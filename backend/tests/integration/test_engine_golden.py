"""Golden / characterization tests for the EV engine.

Each test calls find_ev_opportunities (or compute_match_stats / run_ev_scan) on a
hand-curated scenario board, normalises the output to a deterministic dict, and
compares against a syrupy snapshot.  When engine behaviour intentionally changes,
re-bless with:  pytest --snapshot-update tests/integration/test_engine_golden.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from syrupy.assertion import SnapshotAssertion

from core.engine import compute_match_stats, find_ev_opportunities
from core.ev_pipeline import run_ev_scan

_SCENARIO_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "scenarios"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _load(name: str) -> dict:
    return json.loads((_SCENARIO_DIR / name).read_text())


def _call_engine(scenario: dict) -> list[dict]:
    return find_ev_opportunities(
        scenario["betr_props"],
        scenario["dk_props"],
        fanduel_props=scenario.get("fd_props"),
        espn_props=scenario.get("espn_props"),
    )


def _clean_row(row: dict) -> dict:
    """Snapshot-safe normalised row: round floats, drop non-deterministic timestamps."""
    return {
        "player": row["player"],
        "market": row["market"],
        "line": float(row["line"]),
        "side": row["side"],
        "ev": round(row["ev"], 4),
        "ev_pct": round(row["ev_pct"], 2),
        "side_hit_pct": round(row["side_hit_pct"], 2),
        "plus_ev": row["plus_ev"],
        "line_source": row["line_source"],
        "sharp_books": row["sharp_books"],
        "dk_over_odds": row.get("dk_over_odds"),
        "dk_under_odds": row.get("dk_under_odds"),
        "fd_over_odds": row.get("fd_over_odds"),
        "fd_under_odds": row.get("fd_under_odds"),
        "espn_over_odds": row.get("espn_over_odds"),
        "espn_under_odds": row.get("espn_under_odds"),
        "corroborated": row.get("corroborated"),
        "milestone_admitted": row.get("milestone_admitted"),
    }


def _clean_rows(rows: list[dict]) -> list[dict]:
    return [_clean_row(r) for r in rows]


def _clean_stats(stats: dict) -> dict:
    """Round the float field in match stats for deterministic snapshots."""
    return {**stats, "betr_match_rate_pct": round(stats["betr_match_rate_pct"], 1)}


# ---------------------------------------------------------------------------
# Phase 1, step 4 — one test per scenario
# ---------------------------------------------------------------------------


def test_s1_clean_single_book_ou(snapshot: SnapshotAssertion) -> None:
    """Single DK O/U match at exact Betr line; over is +EV."""
    scenario = _load("s1_clean_single_book_ou.json")
    rows = _call_engine(scenario)
    assert _clean_rows(rows) == snapshot


def test_s2_multi_book_consensus(snapshot: SnapshotAssertion) -> None:
    """DK + FD + ESPN all exact at Betr line → multi_book_consensus adjustment."""
    scenario = _load("s2_multi_book_consensus.json")
    rows = _call_engine(scenario)
    assert _clean_rows(rows) == snapshot
    # Verify the adjustment method is consensus (not just DK)
    assert all(r["line_source"] == "multi_book_consensus" for r in rows if rows)


def test_s3_milestone_devig_admission(snapshot: SnapshotAssertion) -> None:
    """DK milestone ladder, two rungs — ladder-normalised devig, milestone_admitted=True."""
    scenario = _load("s3_milestone_devig_admission.json")
    rows = _call_engine(scenario)
    assert _clean_rows(rows) == snapshot
    plus_ev_rows = [r for r in rows if r["plus_ev"]]
    assert plus_ev_rows, "expected at least one milestone +EV opportunity"
    assert all(r["milestone_admitted"] for r in plus_ev_rows)


def test_s4_o05_hits_total_bases_borrow(snapshot: SnapshotAssertion) -> None:
    """Betr hits o0.5 with no DK hits line — borrows DK total_bases 0.5."""
    scenario = _load("s4_o05_hits_total_bases_borrow.json")
    rows = _call_engine(scenario)
    assert _clean_rows(rows) == snapshot
    assert rows, "borrow should produce at least one opportunity"


def test_s5_event_hour_doubleheader_split(snapshot: SnapshotAssertion) -> None:
    """Doubleheader: Betr at 17:00 matches only the DK prop sharing hour 17, not 23."""
    scenario = _load("s5_event_hour_doubleheader_split.json")
    rows = _call_engine(scenario)
    assert _clean_rows(rows) == snapshot
    # Must have matched exactly one game (the 17:xx DK prop)
    assert rows, "expected a match to the 17-hour DK prop"
    # DK at hour 23 must NOT appear — over_odds for that prop is -135
    over_rows = [r for r in rows if r["side"] == "over"]
    assert over_rows, "expected over opportunity"
    dk_over = over_rows[0]["dk_over_odds"]
    assert dk_over == -140, f"expected DK -140 (hour 17 prop), got {dk_over}"


def test_s6_ambiguous_sharp_ladder_collision(snapshot: SnapshotAssertion) -> None:
    """Conflicting DK odds at same player|market|hour|line → collision drop, 0 opps."""
    scenario = _load("s6_ambiguous_sharp_ladder_collision.json")
    rows = _call_engine(scenario)
    assert rows == []
    assert rows == snapshot


def test_s7_live_vs_pregame_gate(snapshot: SnapshotAssertion) -> None:
    """Live Betr prop cannot match pregame DK — |live key suffix gates it out."""
    scenario = _load("s7_live_vs_pregame_gate.json")
    rows = _call_engine(scenario)
    assert rows == []
    assert rows == snapshot


# ---------------------------------------------------------------------------
# Phase 1, step 5 — compute_match_stats snapshot (multi-prop scenario)
# ---------------------------------------------------------------------------


def test_match_stats_multi_prop_snapshot(snapshot: SnapshotAssertion) -> None:
    """compute_match_stats snapshot on a two-player board — tracks match-rate regressions."""
    # One matched player (Aaron Judge) + one unmatched (Betr-only player)
    betr_props = [
        {
            "sportsbook": "Betr",
            "player": "Aaron Judge",
            "market": "hits",
            "line": 1.5,
            "league": "MLB",
            "over_odds": -120,
            "under_odds": -120,
            "event_start": "2026-07-01T18:00:00.000Z",
        },
        {
            "sportsbook": "Betr",
            "player": "Unmatched Player",
            "market": "hits",
            "line": 1.5,
            "league": "MLB",
            "over_odds": -120,
            "under_odds": -120,
            "event_start": "2026-07-01T18:00:00.000Z",
        },
    ]
    dk_props = [
        {
            "sportsbook": "DraftKings",
            "player": "Aaron Judge",
            "market": "hits",
            "line": 1.5,
            "league": "MLB",
            "over_odds": -140,
            "under_odds": 120,
            "is_main_line": True,
            "event_start": "2026-07-01T18:05:00.000Z",
        }
    ]
    stats = compute_match_stats(betr_props, dk_props)
    assert _clean_stats(stats) == snapshot
    assert stats["matched_keys"] == 1
    assert stats["betr_match_rate_pct"] == 50.0


# ---------------------------------------------------------------------------
# Phase 1, step 6 — normalize → scan structural invariants
# ---------------------------------------------------------------------------


def test_run_ev_scan_structural_invariants(tmp_path: Path) -> None:
    """Every plus_ev row from run_ev_scan has required structural fields."""
    betr_board = [
        {
            "sportsbook": "Betr",
            "player": "Aaron Judge",
            "market": "hits",
            "line": 1.5,
            "league": "MLB",
            "over_odds": -120,
            "under_odds": -120,
            "event_start": "2026-07-01T18:00:00.000Z",
        },
        {
            "sportsbook": "Betr",
            "player": "Shohei Ohtani",
            "market": "strikeouts",
            "line": 6.5,
            "league": "MLB",
            "over_odds": -120,
            "under_odds": -120,
            "event_start": "2026-07-01T21:00:00.000Z",
        },
    ]
    dk_board = [
        {
            "sportsbook": "DraftKings",
            "player": "Aaron Judge",
            "market": "hits",
            "line": 1.5,
            "league": "MLB",
            "over_odds": -140,
            "under_odds": 120,
            "is_main_line": True,
            "event_start": "2026-07-01T18:05:00.000Z",
        },
        {
            "sportsbook": "DraftKings",
            "player": "Shohei Ohtani",
            "market": "strikeouts",
            "line": 6.5,
            "league": "MLB",
            "over_odds": -120,
            "under_odds": -115,
            "is_main_line": True,
            "event_start": "2026-07-01T21:05:00.000Z",
        },
    ]
    (tmp_path / "betr_normalized.json").write_text(json.dumps(betr_board), encoding="utf-8")
    (tmp_path / "dk_normalized.json").write_text(json.dumps(dk_board), encoding="utf-8")

    rows = run_ev_scan(tmp_path, normalize_first=False)

    assert rows, "expected at least one opportunity from the two-player board"
    for row in rows:
        if row.get("plus_ev"):
            assert row.get("line_source") is not None, f"plus_ev row missing line_source: {row}"
            assert row.get("sharp_books"), f"plus_ev row has empty sharp_books: {row}"
            has_odds = any(
                row.get(k) is not None
                for k in ("dk_over_odds", "dk_under_odds", "fd_over_odds", "espn_over_odds")
            )
            assert has_odds, f"plus_ev row has no book odds: {row}"
