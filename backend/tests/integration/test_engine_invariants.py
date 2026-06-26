"""Determinism and robustness invariants for engine entrypoints.

These tests do NOT snapshot specific values; they assert structural
properties that must hold for any valid input.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.engine import find_ev_opportunities
from core.ev_pipeline import run_ev_scan

_SCENARIO_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "scenarios"

_EVENT_START = "2026-07-01T18:00:00.000Z"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _betr(player: str, market: str, line: float, **kw) -> dict:
    return {
        "sportsbook": "Betr",
        "player": player,
        "market": market,
        "line": line,
        "over_odds": -120,
        "under_odds": -120,
        "event_start": _EVENT_START,
        **kw,
    }


def _dk(player: str, market: str, line: float, over: int = -130, under: int = 110) -> dict:
    return {
        "sportsbook": "DraftKings",
        "player": player,
        "market": market,
        "line": line,
        "over_odds": over,
        "under_odds": under,
        "is_main_line": True,
        "event_start": _EVENT_START,
    }


def _round_row(row: dict) -> dict:
    return {k: (round(v, 6) if isinstance(v, float) else v) for k, v in row.items()}


def _normalise_results(rows: list[dict]) -> list[dict]:
    return [_round_row(r) for r in rows]


# ---------------------------------------------------------------------------
# Phase 6, step 1 — idempotency
# ---------------------------------------------------------------------------


def test_find_ev_opportunities_idempotent_single_book() -> None:
    """Same input twice → byte-identical rounded output (no dict/set ordering churn)."""
    betr = [_betr("Aaron Judge", "hits", 1.5), _betr("Shohei Ohtani", "strikeouts", 6.5)]
    dk = [_dk("Aaron Judge", "hits", 1.5), _dk("Shohei Ohtani", "strikeouts", 6.5)]

    run1 = _normalise_results(find_ev_opportunities(betr, dk))
    run2 = _normalise_results(find_ev_opportunities(betr, dk))
    assert run1 == run2


def test_find_ev_opportunities_idempotent_multi_book() -> None:
    """Multi-book path is also idempotent."""
    betr = [_betr("Shohei Ohtani", "strikeouts", 6.5)]
    dk = [_dk("Shohei Ohtani", "strikeouts", 6.5)]
    fd = [{
        "sportsbook": "FanDuel",
        "player": "Shohei Ohtani",
        "market": "strikeouts",
        "line": 6.5,
        "over_odds": -120,
        "under_odds": -110,
        "is_main_line": True,
        "event_start": _EVENT_START,
    }]

    run1 = _normalise_results(find_ev_opportunities(betr, dk, fanduel_props=fd))
    run2 = _normalise_results(find_ev_opportunities(betr, dk, fanduel_props=fd))
    assert run1 == run2


def test_run_ev_scan_idempotent(tmp_path: Path) -> None:
    """run_ev_scan on same files twice → same set of (player, market, line, side) rows."""
    betr_board = [_betr("Aaron Judge", "hits", 1.5)]
    dk_board = [_dk("Aaron Judge", "hits", 1.5)]
    (tmp_path / "betr_normalized.json").write_text(json.dumps(betr_board), encoding="utf-8")
    (tmp_path / "dk_normalized.json").write_text(json.dumps(dk_board), encoding="utf-8")

    rows1 = run_ev_scan(tmp_path, normalize_first=False)
    rows2 = run_ev_scan(tmp_path, normalize_first=False)

    keys1 = [(r["player"], r["market"], r["line"], r["side"]) for r in rows1]
    keys2 = [(r["player"], r["market"], r["line"], r["side"]) for r in rows2]
    assert keys1 == keys2


# ---------------------------------------------------------------------------
# Phase 6, step 2 — defensive inputs (never raises, returns clean result)
# ---------------------------------------------------------------------------


def test_find_ev_opportunities_empty_board_returns_empty() -> None:
    assert find_ev_opportunities([], []) == []


def test_find_ev_opportunities_empty_betr_returns_empty() -> None:
    dk = [_dk("Aaron Judge", "hits", 1.5)]
    assert find_ev_opportunities([], dk) == []


def test_find_ev_opportunities_empty_dk_returns_empty() -> None:
    betr = [_betr("Aaron Judge", "hits", 1.5)]
    assert find_ev_opportunities(betr, []) == []


def test_find_ev_opportunities_single_book_only_no_raise() -> None:
    """Single sharp book with no Betr match → empty, no exception."""
    dk = [_dk("Unknown Player", "hits", 1.5)]
    result = find_ev_opportunities([], dk)
    assert result == []


def test_find_ev_opportunities_missing_event_start_pregame_skipped() -> None:
    """Pregame Betr prop with no event_start is skipped — no KeyError."""
    betr = [
        {
            "sportsbook": "Betr",
            "player": "X",
            "market": "hits",
            "line": 1.5,
            "over_odds": -120,
            "under_odds": -120,
            # intentionally no event_start and no is_live
        }
    ]
    dk = [_dk("X", "hits", 1.5)]
    result = find_ev_opportunities(betr, dk)
    assert result == []


def test_find_ev_opportunities_malformed_row_no_raise() -> None:
    """Row with all required fields but nonsensical odds still doesn't raise."""
    betr = [_betr("Player A", "hits", 1.5, over_odds=-100000, under_odds=-100000)]
    dk = [_dk("Player A", "hits", 1.5, over=-100000, under=-100000)]
    result = find_ev_opportunities(betr, dk)
    assert isinstance(result, list)


def test_find_ev_opportunities_none_odds_side_not_produced() -> None:
    """If Betr prop has no over_odds, no over opportunity is produced."""
    betr = [
        {
            "sportsbook": "Betr",
            "player": "Aaron Judge",
            "market": "hits",
            "line": 1.5,
            "over_odds": None,
            "under_odds": -120,
            "event_start": _EVENT_START,
        }
    ]
    dk = [_dk("Aaron Judge", "hits", 1.5)]
    rows = find_ev_opportunities(betr, dk)
    assert rows, "expected under-side opportunity to be produced when over_odds is None"
    assert all(r["side"] == "under" for r in rows)


def test_run_ev_scan_returns_empty_when_no_betr_props(tmp_path: Path) -> None:
    """run_ev_scan logs error and returns [] when betr board is empty."""
    (tmp_path / "betr_normalized.json").write_text("[]", encoding="utf-8")
    (tmp_path / "dk_normalized.json").write_text(
        json.dumps([_dk("x", "hits", 1.5)]), encoding="utf-8"
    )
    result = run_ev_scan(tmp_path, normalize_first=False)
    assert result == []


def test_run_ev_scan_returns_empty_when_no_sharp_props(tmp_path: Path) -> None:
    """run_ev_scan returns [] when all sharp boards are empty."""
    (tmp_path / "betr_normalized.json").write_text(
        json.dumps([_betr("x", "hits", 1.5)]), encoding="utf-8"
    )
    result = run_ev_scan(tmp_path, normalize_first=False)
    assert result == []
