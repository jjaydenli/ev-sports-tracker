"""Scrape-job publisher: which runs carry a board, what reaches the public log, retries.

Oracle: the Decision 4 rule (board only when exit 0, same ``run_id``, at least one row)
and the publisher contract in the live-web-board design. Data dirs are written with the
pipeline's own ``write_scrape_coverage``/``save_wrapped_board``; HTTP goes through
``httpx.MockTransport``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from core.pipeline_artifacts import (
    EV_OUTPUT_FILENAME,
    SCRAPE_COVERAGE_FILENAME,
    save_wrapped_board,
    write_scrape_coverage,
)
from web.models import RunPayload
from web.publish import build_run_payload, main

API_URL = "https://board.test"
PUSH_TOKEN = "push-token"

_HEALTHY_SOURCES = {
    "betr:NBA": {"source": "betr", "league": "NBA", "status": "ok", "prop_count": 243},
    "dk:NBA": {"source": "dk", "league": "NBA", "status": "ok", "prop_count": 365,
               "requests": 40, "blocked_requests": 0},
    "fd:NBA": {"source": "fd", "league": "NBA", "status": "ok", "prop_count": 236},
}
_PARTIAL_DK_BLOCK = {
    **_HEALTHY_SOURCES,
    "dk:NBA": {**_HEALTHY_SOURCES["dk:NBA"], "prop_count": 70, "blocked_requests": 3},
}
_FULL_DK_BLOCK = {
    **_HEALTHY_SOURCES,
    "dk:NBA": {"source": "dk", "league": "NBA", "status": "failed", "reason": "blocked",
               "prop_count": 0, "requests": 40, "blocked_requests": 40},
}
_AUTH_FAILURE = {
    "betr:NBA": {"source": "betr", "league": "NBA", "status": "failed", "reason": "auth",
                 "error": "Offline user session not found", "prop_count": 0},
}


def _write_coverage(data_dir: Path, run_id: str, sources: dict[str, dict]) -> None:
    write_scrape_coverage(
        data_dir / SCRAPE_COVERAGE_FILENAME,
        run_id=run_id,
        mode="full",
        dfs_sources=("betr",),
        book_sources=("dk", "fd"),
        leagues=("NBA",),
        sources=sources,
        ev_eligible=True,
    )


def _write_board(data_dir: Path, run_id: str, rows: list[dict]) -> None:
    save_wrapped_board(data_dir / EV_OUTPUT_FILENAME, run_id=run_id, props=rows)


# (id, exit_code, coverage (run_id, sources) or None, board (run_id, has_rows) or None,
#  expected outcome). The board is attached exactly when the outcome is "ok".
_CASES = [
    ("healthy", 0, ("run-2", _HEALTHY_SOURCES), ("run-2", True), "ok"),
    ("partial-dk-block", 0, ("run-2", _PARTIAL_DK_BLOCK), ("run-2", True), "ok"),
    ("full-dk-block-fd-priced", 0, ("run-2", _FULL_DK_BLOCK), ("run-2", True), "ok"),
    # A dead token writes fresh coverage and exits 1 before the wipe: the last board stays.
    ("betr-auth-failure", 1, ("run-2", _AUTH_FAILURE), ("run-1", True), "failed"),
    # --scrape-only exits 0 and does not wipe or rewrite the EV board.
    ("exit-0-board-from-older-run", 0, ("run-2", _HEALTHY_SOURCES), ("run-1", True), "failed"),
    ("exit-0-no-board-file", 0, ("run-2", _HEALTHY_SOURCES), None, "failed"),
    ("crash-after-board-written", 1, ("run-2", _HEALTHY_SOURCES), ("run-2", True), "failed"),
    ("no-props-posted-yet", 0, ("run-2", _HEALTHY_SOURCES), ("run-2", False), "empty"),
    ("zero-rows-on-failed-run", 1, ("run-2", _HEALTHY_SOURCES), ("run-2", False), "failed"),
]


@pytest.mark.parametrize(
    ("exit_code", "coverage", "board", "expected_outcome"),
    [case[1:] for case in _CASES],
    ids=[case[0] for case in _CASES],
)
def test_board_attached_only_for_a_clean_run_with_rows(
    tmp_path: Path,
    s1_ev_rows: list[dict],
    exit_code: int,
    coverage: tuple[str, dict[str, dict]],
    board: tuple[str, bool] | None,
    expected_outcome: str,
) -> None:
    coverage_run_id, sources = coverage
    _write_coverage(tmp_path, coverage_run_id, sources)
    if board is not None:
        board_run_id, has_rows = board
        _write_board(tmp_path, board_run_id, s1_ev_rows if has_rows else [])

    payload = build_run_payload(tmp_path, exit_code)

    assert payload["run_id"] == coverage_run_id
    assert payload["exit_code"] == exit_code
    assert payload["outcome"] == expected_outcome
    assert payload["coverage"] == json.loads((tmp_path / SCRAPE_COVERAGE_FILENAME).read_text())
    if expected_outcome == "ok":
        assert payload["board"] == {"run_id": coverage_run_id, "props": s1_ev_rows}
    else:
        assert payload["board"] is None
    RunPayload.model_validate(payload)


def test_missing_coverage_is_a_failed_run_with_empty_health(
    tmp_path: Path, s1_ev_rows: list[dict]
) -> None:
    """A crash before coverage is written; a leftover board must still not be attached."""
    _write_board(tmp_path, "run-1", s1_ev_rows)

    payload = build_run_payload(tmp_path, 0)

    assert payload["run_id"].startswith("nocoverage-")
    assert payload["outcome"] == "failed"
    assert payload["coverage"] == {}
    assert payload["board"] is None
    RunPayload.model_validate(payload)


@pytest.fixture
def push_env(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    monkeypatch.setenv("BOARD_API_URL", API_URL)
    monkeypatch.setenv("BOARD_PUSH_TOKEN", PUSH_TOKEN)
    sleeps: list[float] = []
    monkeypatch.setattr("web.publish.time.sleep", sleeps.append)
    return sleeps


def _healthy_dir(data_dir: Path, rows: list[dict]) -> Path:
    _write_coverage(data_dir, "run-2", _HEALTHY_SOURCES)
    _write_board(data_dir, "run-2", rows)
    return data_dir


def _argv(data_dir: Path, exit_code: int = 0) -> list[str]:
    return ["--exit-code", str(exit_code), "--data-dir", str(data_dir)]


def _transport(responses: list[Callable[[httpx.Request], httpx.Response]]) -> tuple[
    httpx.MockTransport, list[httpx.Request]
]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return responses[len(seen) - 1](request)

    return httpx.MockTransport(handler), seen


def _status(code: int) -> Callable[[httpx.Request], httpx.Response]:
    return lambda request: httpx.Response(code, json={"run_id": "run-2", "outcome": "ok"})


def _connect_error(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


def test_main_posts_the_run_and_logs_no_prop(
    tmp_path: Path,
    s1_ev_rows: list[dict],
    push_env: list[float],
    capsys: pytest.CaptureFixture[str],
) -> None:
    data_dir = _healthy_dir(tmp_path, s1_ev_rows)
    transport, seen = _transport([_status(200)])

    assert main(_argv(data_dir), transport=transport) == 0

    (request,) = seen
    assert request.method == "POST"
    assert str(request.url) == f"{API_URL}/api/runs"
    assert request.headers["Authorization"] == f"Bearer {PUSH_TOKEN}"
    sent = RunPayload.model_validate_json(request.content)
    assert sent.outcome == "ok"
    assert sent.board is not None and sent.board.props == s1_ev_rows

    out = capsys.readouterr()
    lines = out.out.strip().splitlines()
    assert len(lines) == 1
    assert "betr:NBA=ok(243)" in lines[0]
    assert "outcome=ok" in lines[0]
    players = {row["player"] for row in s1_ev_rows}
    assert players
    for player in players:
        assert player not in out.out
        assert player not in out.err


@pytest.mark.parametrize(
    ("responses", "expected_exit", "expected_requests"),
    [
        ([_status(503), _status(200)], 0, 2),
        ([_connect_error, _status(200)], 0, 2),
        ([_status(503), _status(503)], 1, 2),
        ([_status(401)], 1, 1),
    ],
    ids=["5xx-then-ok", "connect-error-then-ok", "5xx-twice", "4xx-not-retried"],
)
def test_main_retries_once_on_cold_start(
    tmp_path: Path,
    s1_ev_rows: list[dict],
    push_env: list[float],
    responses: list[Callable[[httpx.Request], httpx.Response]],
    expected_exit: int,
    expected_requests: int,
) -> None:
    transport, seen = _transport(responses)

    assert main(_argv(_healthy_dir(tmp_path, s1_ev_rows)), transport=transport) == expected_exit
    assert len(seen) == expected_requests


def test_main_without_api_env_fails_without_posting(
    tmp_path: Path, s1_ev_rows: list[dict], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("BOARD_API_URL", raising=False)
    monkeypatch.setenv("BOARD_PUSH_TOKEN", PUSH_TOKEN)
    transport, seen = _transport([_status(200)])

    assert main(_argv(_healthy_dir(tmp_path, s1_ev_rows)), transport=transport) == 1
    assert seen == []
