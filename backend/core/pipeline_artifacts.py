"""Pipeline artifact paths, wipe rules, and wrapped JSON I/O."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.pipeline_sources import BOOK_SOURCES, DFS_SOURCES, PIPELINE_LEAGUES
from core.ev_run_diff import EV_DIFF_FILENAME, EV_PREVIOUS_FILENAME

SCRAPE_COVERAGE_FILENAME = "scrape_coverage.json"

EV_OUTPUT_FILENAME = "ev_opportunities.json"
MATCH_REPORT_FILENAME = "match_report.json"
UNMATCHED_BETR_FILENAME = "unmatched_betr.json"
UNMATCHED_DK_FILENAME = "unmatched_dk.json"
BETR_NORMALIZED = "betr_normalized.json"
DK_NORMALIZED = "dk_normalized.json"
FD_NORMALIZED = "fd_normalized.json"
ESPN_NORMALIZED = "espn_normalized.json"
UNIFIED_OUTPUT_FILENAME = "unified_master_board.json"

SCRAPE_COVERAGE_FILENAME = "scrape_coverage.json"

MASTER_BOARD_BY_SOURCE: dict[str, str] = {
    "betr": "betr_master_board.json",
    "dk": "dk_master_board.json",
    "fd": "fd_master_board.json",
    "espn": "espn_master_board.json",
}

NORMALIZED_BY_SOURCE: dict[str, str] = {
    "betr": BETR_NORMALIZED,
    "dk": DK_NORMALIZED,
    "fd": FD_NORMALIZED,
    "espn": ESPN_NORMALIZED,
}

EV_ARTIFACTS: tuple[str, ...] = (
    EV_OUTPUT_FILENAME,
    EV_PREVIOUS_FILENAME,
    EV_DIFF_FILENAME,
    MATCH_REPORT_FILENAME,
    UNMATCHED_BETR_FILENAME,
    UNMATCHED_DK_FILENAME,
    SCRAPE_COVERAGE_FILENAME,
)

SHARED_ARTIFACTS: tuple[str, ...] = (UNIFIED_OUTPUT_FILENAME,)


def all_pipeline_artifacts() -> tuple[str, ...]:
    """All files owned by a full pipeline run."""
    masters = tuple(MASTER_BOARD_BY_SOURCE.values())
    normalized = tuple(NORMALIZED_BY_SOURCE.values())
    return masters + normalized + SHARED_ARTIFACTS + EV_ARTIFACTS


def artifacts_for_sources(
    dfs_sources: tuple[str, ...],
    book_sources: tuple[str, ...],
    *,
    include_ev: bool,
    include_shared: bool,
) -> list[str]:
    """Files to remove before a partial or full scrape."""
    paths: list[str] = []
    for source in dfs_sources:
        paths.append(MASTER_BOARD_BY_SOURCE[source])
        paths.append(NORMALIZED_BY_SOURCE[source])
    for source in book_sources:
        paths.append(MASTER_BOARD_BY_SOURCE[source])
        paths.append(NORMALIZED_BY_SOURCE[source])
    if include_shared:
        paths.extend(SHARED_ARTIFACTS)
    if include_ev:
        paths.extend(EV_ARTIFACTS)
    return paths


def wipe_files(data_dir: Path, filenames: list[str]) -> None:
    """Delete artifact files if they exist."""
    for name in filenames:
        path = data_dir / name
        if path.exists():
            path.unlink()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_wrapped_board(
    path: Path,
    *,
    run_id: str,
    props: list[dict],
) -> None:
    """Write master or normalized board with run metadata."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id,
        "generated_at": utc_now_iso(),
        "props": props,
    }
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=4)


def load_wrapped_board(path: Path) -> tuple[str | None, list[dict]]:
    """
    Load props from a board file.

    Supports wrapped ``{run_id, props}`` and legacy bare lists.
    """
    if not path.exists():
        return None, []

    with path.open(encoding="utf-8") as file:
        data = json.load(file)

    if isinstance(data, list):
        return None, data
    if isinstance(data, dict):
        props = data.get("props")
        if isinstance(props, list):
            run_id = data.get("run_id")
            return (str(run_id) if run_id else None), props
    return None, []


def assert_run_id(path: Path, expected_run_id: str, *, label: str) -> list[dict]:
    """Load props and fail if run_id does not match (fresh-only runs)."""
    run_id, props = load_wrapped_board(path)
    if run_id != expected_run_id:
        raise ValueError(
            f"{label} run_id mismatch: file has {run_id!r}, expected {expected_run_id!r}"
        )
    return props


def write_scrape_coverage(
    path: Path,
    *,
    run_id: str,
    mode: str,
    dfs_sources: tuple[str, ...],
    book_sources: tuple[str, ...],
    leagues: tuple[str, ...],
    sources: dict[str, dict[str, Any]],
    ev_eligible: bool,
    previous_run_id: str | None = None,
) -> None:
    """Persist scrape coverage and run metadata."""
    payload = {
        "run_id": run_id,
        "generated_at": utc_now_iso(),
        "mode": mode,
        "dfs": list(dfs_sources),
        "books": list(book_sources),
        "leagues": list(leagues),
        "sources": sources,
        "ev": {
            "eligible": ev_eligible,
            "previous_run_id": previous_run_id,
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)


def default_full_run_sources() -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Default dfs, books, and leagues for a full ``./ev`` run."""
    return DFS_SOURCES, BOOK_SOURCES, PIPELINE_LEAGUES
