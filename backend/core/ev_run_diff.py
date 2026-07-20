"""Compare consecutive top-N EV scan outputs (run-over-run diff).

``removed`` rows may have been outranked or filtered by ``min_ev`` / ``top_n``,
not necessarily dropped from the Betr board.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.engine import build_prop_key

EV_PREVIOUS_FILENAME = "ev_opportunities.previous.json"
EV_DIFF_FILENAME = "ev_run_diff.json"


def build_opportunity_row_id(row: dict) -> str:
    """Stable id for a ranked opportunity row: player|market|line|side."""
    side = str(row.get("side", "")).strip().lower()
    return f"{build_prop_key(row)}|{side}"


def index_opportunities_by_id(rows: list[dict]) -> dict[str, dict]:
    """Map row id → row; first occurrence wins on duplicates."""
    indexed: dict[str, dict] = {}
    for row in rows:
        row_id = build_opportunity_row_id(row)
        if row_id not in indexed:
            indexed[row_id] = row
    return indexed


def _snapshot_row(row: dict) -> dict[str, Any]:
    """Fields preserved for diff JSON and CLI."""
    return {
        "player": row.get("player"),
        "market": row.get("market"),
        "line": row.get("line"),
        "side": row.get("side"),
        "ev": row.get("ev"),
        "ev_pct": row.get("ev_pct"),
        "side_hit_pct": row.get("side_hit_pct"),
        "dk_over_odds": row.get("dk_over_odds"),
        "dk_under_odds": row.get("dk_under_odds"),
        "fd_over_odds": row.get("fd_over_odds"),
        "fd_under_odds": row.get("fd_under_odds"),
    }


def _changed_entry(
    row_id: str,
    *,
    previous: dict,
    current: dict,
) -> dict[str, Any]:
    prev_ev = float(previous.get("ev") or 0)
    curr_ev = float(current.get("ev") or 0)
    prev_pct = previous.get("ev_pct")
    curr_pct = current.get("ev_pct")
    return {
        "id": row_id,
        "ev_delta": round(curr_ev - prev_ev, 4),
        "ev_pct_delta": round(float(curr_pct) - float(prev_pct), 2)
        if prev_pct is not None and curr_pct is not None
        else None,
        "previous": _snapshot_row(previous),
        "current": _snapshot_row(current),
    }


def compute_run_diff(
    previous: list[dict],
    current: list[dict],
) -> dict[str, Any]:
    """Bucket top-N rows into new, removed, improved, and fell."""
    prev_by_id = index_opportunities_by_id(previous)
    curr_by_id = index_opportunities_by_id(current)
    prev_ids = set(prev_by_id)
    curr_ids = set(curr_by_id)

    new_rows = [
        {"id": row_id, **_snapshot_row(curr_by_id[row_id])}
        for row_id in sorted(curr_ids - prev_ids)
    ]
    removed_rows = [
        {"id": row_id, **_snapshot_row(prev_by_id[row_id])}
        for row_id in sorted(prev_ids - curr_ids)
    ]

    improved: list[dict] = []
    fell: list[dict] = []
    for row_id in sorted(prev_ids & curr_ids):
        prev_row = prev_by_id[row_id]
        curr_row = curr_by_id[row_id]
        prev_ev = float(prev_row.get("ev") or 0)
        curr_ev = float(curr_row.get("ev") or 0)
        if curr_ev > prev_ev:
            improved.append(
                _changed_entry(row_id, previous=prev_row, current=curr_row)
            )
        elif curr_ev < prev_ev:
            fell.append(_changed_entry(row_id, previous=prev_row, current=curr_row))

    return {
        "has_previous": bool(previous),
        "new": new_rows,
        "removed": removed_rows,
        "improved": improved,
        "fell": fell,
    }


def rotate_ev_opportunities_file(
    data_dir: Path,
    *,
    current_filename: str = "ev_opportunities.json",
    previous_filename: str = EV_PREVIOUS_FILENAME,
) -> tuple[list[dict], str | None]:
    """
    If current output exists, read it, rotate to previous, return prior rows.

    Returns ``(previous_rows, previous_run_id)``. Empty list when no prior run.
    """
    current_path = data_dir / current_filename
    if not current_path.exists():
        return [], None

    with current_path.open(encoding="utf-8") as file:
        data = json.load(file)

    if isinstance(data, list):
        previous_rows = data
        prior_run_id = None
    elif isinstance(data, dict):
        props = data.get("props")
        previous_rows = props if isinstance(props, list) else []
        raw_id = data.get("run_id")
        prior_run_id = str(raw_id) if raw_id else None
    else:
        previous_rows = []
        prior_run_id = None

    previous_path = data_dir / previous_filename
    if previous_path.exists():
        previous_path.unlink()
    current_path.rename(previous_path)
    return previous_rows, prior_run_id


def _format_player_line(entry: dict) -> str:
    player = str(entry.get("player") or entry.get("previous", {}).get("player") or "")
    market = str(entry.get("market") or entry.get("previous", {}).get("market") or "")
    line = entry.get("line")
    if line is None and "previous" in entry:
        line = entry["previous"].get("line")
    side = str(entry.get("side") or entry.get("current", {}).get("side") or "").upper()
    line_text = (
        str(int(line))
        if line is not None and float(line) == int(float(line))
        else str(line)
    )
    return f"{player} {side} {market} {line_text}".strip()


def format_run_diff_summary(diff: dict[str, Any]) -> str:
    """Compact CLI block: NEW / RM / UP / DN sections."""
    if not diff.get("has_previous"):
        return ""

    lines = ["run diff (vs previous top-N):"]

    def append_bucket(label: str, items: list[dict], detail_fn) -> None:
        if not items:
            return
        lines.append(f"  {label} ({len(items)})")
        for item in items:
            lines.append(f"    {detail_fn(item)}")

    append_bucket(
        "NEW",
        diff.get("new") or [],
        lambda e: (
            f"{_format_player_line(e)} ev={e.get('ev_pct'):+.1f}%"
            if e.get("ev_pct") is not None
            else _format_player_line(e)
        ),
    )
    append_bucket(
        "RM",
        diff.get("removed") or [],
        lambda e: _format_player_line(e),
    )
    append_bucket(
        "UP",
        diff.get("improved") or [],
        lambda e: (
            f"{_format_player_line(e)} "
            f"ev {e['previous'].get('ev_pct'):+.1f}%→{e['current'].get('ev_pct'):+.1f}%"
        ),
    )
    append_bucket(
        "DN",
        diff.get("fell") or [],
        lambda e: (
            f"{_format_player_line(e)} "
            f"ev {e['previous'].get('ev_pct'):+.1f}%→{e['current'].get('ev_pct'):+.1f}%"
        ),
    )

    if len(lines) == 1:
        lines.append("  (no changes)")
    return "\n".join(lines)


def write_run_diff_json(diff: dict[str, Any], path: Path) -> None:
    """Persist diff buckets under data/processed."""
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        **diff,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)
