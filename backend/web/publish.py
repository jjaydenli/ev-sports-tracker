"""Post one scrape run's health, and its board when the run produced one, to the board API.

Run by the scheduled workflow after ``./ev``, from ``backend``::

    python -m web.publish --exit-code "$EV_EXIT_CODE"

Env: ``BOARD_API_URL``, ``BOARD_PUSH_TOKEN``. Workflow logs are public, so this prints
one coverage line and never a prop.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from core.pipeline_artifacts import (
    EV_OUTPUT_FILENAME,
    SCRAPE_COVERAGE_FILENAME,
    format_coverage_summary,
    load_wrapped_board,
    utc_now_iso,
)
from core.pipeline_runner import DEFAULT_DATA_DIR

# Render's free web service takes about a minute to wake from sleep.
POST_TIMEOUT_S = 150.0
RETRY_DELAY_S = 10.0
# ``./ev --top-n all`` is uncapped, so the bound on what one POST carries sits here: about
# 5x the largest board seen (~1.2 KB a row). Capped here, not rejected by the API, so an
# oversized board never costs the run its health record.
MAX_PUBLISHED_ROWS = 2000


def build_run_payload(data_dir: Path, exit_code: int) -> dict[str, Any]:
    """Run envelope for ``POST /api/runs``.

    The board is attached only when ``./ev`` exited 0, the board's ``run_id`` is this
    run's, and it has at least one row. Anything else is health only, so the site keeps
    its last good board.
    """
    coverage_path = data_dir / SCRAPE_COVERAGE_FILENAME
    if not coverage_path.exists():
        now = utc_now_iso()
        return {
            "run_id": f"nocoverage-{now}",
            "generated_at": now,
            "exit_code": exit_code,
            "outcome": "failed",
            "coverage": {},
            "board": None,
        }

    coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    run_id = str(coverage["run_id"])
    board_run_id, props = load_wrapped_board(data_dir / EV_OUTPUT_FILENAME)
    clean_run = exit_code == 0 and board_run_id == run_id

    board = None
    if clean_run and props:
        outcome = "ok"
        board = {"run_id": run_id, "props": props}
    elif clean_run:
        outcome = "empty"
    else:
        outcome = "failed"

    return {
        "run_id": run_id,
        "generated_at": coverage.get("generated_at") or utc_now_iso(),
        "exit_code": exit_code,
        "outcome": outcome,
        "coverage": coverage,
        "board": board,
    }


def cap_board_rows(payload: dict[str, Any], max_rows: int = MAX_PUBLISHED_ROWS) -> int:
    """Keep the board's first ``max_rows`` rows (already ranked by EV); return how many
    were dropped."""
    board = payload.get("board")
    if not board:
        return 0
    props = board["props"]
    dropped = max(len(props) - max_rows, 0)
    board["props"] = props[:max_rows]
    return dropped


def post_run(
    payload: dict[str, Any],
    *,
    api_url: str,
    token: str,
    transport: httpx.BaseTransport | None = None,
) -> str | None:
    """POST the run, retrying once on a connection error or 5xx.

    Returns ``None`` on a 2xx, else a short failure description (no payload content).
    """
    url = f"{api_url.rstrip('/')}/api/runs"
    headers = {"Authorization": f"Bearer {token}"}
    failure = "not attempted"
    with httpx.Client(transport=transport, timeout=POST_TIMEOUT_S) as client:
        for attempt in range(2):
            if attempt:
                time.sleep(RETRY_DELAY_S)
            try:
                response = client.post(url, json=payload, headers=headers)
            except httpx.TransportError as exc:
                failure = type(exc).__name__
                continue
            if response.is_success:
                return None
            failure = f"HTTP {response.status_code}"
            if not response.is_server_error:
                break
    return failure


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m web.publish",
        description="Publish the latest ./ev run to the board API.",
    )
    parser.add_argument("--exit-code", type=int, required=True, help="./ev exit code")
    parser.add_argument("--data-dir", type=Path, default=Path(DEFAULT_DATA_DIR))
    return parser


def main(
    argv: list[str] | None = None, *, transport: httpx.BaseTransport | None = None
) -> int:
    args = build_parser().parse_args(argv)
    api_url = os.getenv("BOARD_API_URL")
    token = os.getenv("BOARD_PUSH_TOKEN")
    if not api_url or not token:
        print("publish: BOARD_API_URL and BOARD_PUSH_TOKEN must be set", file=sys.stderr)
        return 1

    payload = build_run_payload(args.data_dir, args.exit_code)
    dropped = cap_board_rows(payload)
    failure = post_run(payload, api_url=api_url, token=token, transport=transport)
    summary = format_coverage_summary(payload["coverage"].get("sources") or {})
    published = "ok" if failure is None else f"failed({failure})"
    truncated = f" truncated={dropped}" if dropped else ""
    print(f"{summary} outcome={payload['outcome']} publish={published}{truncated}")
    return 0 if failure is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
