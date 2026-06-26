"""Phase 8 — Cross-book matching characterization golden snapshots.

1. ``compute_match_stats`` across the full Phase 1 scenario matrix so any
   silent change to match-key logic or the collision/live gates fails here.

2. Team-abbreviation canon golden: DK emits "CWS@NYY" (non-canonical),
   Betr emits "CHW@NYY" (canonical).  Matching keys on player|market|event_hour,
   not game string — so the engine must still produce an opportunity and the
   output ``game`` must carry the canonical Betr form.

Re-bless with:
    pytest --snapshot-update tests/integration/test_match_stats_golden.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from syrupy.assertion import SnapshotAssertion

from core.engine import compute_match_stats, find_ev_opportunities

_SCENARIO_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "scenarios"

_EVENT_START_A = "2026-07-01T18:00:00.000Z"
_EVENT_START_B = "2026-07-01T18:05:00.000Z"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _load(name: str) -> dict:
    return json.loads((_SCENARIO_DIR / name).read_text(encoding="utf-8"))


def _clean_stats(stats: dict) -> dict:
    return {**stats, "betr_match_rate_pct": round(stats["betr_match_rate_pct"], 1)}


# ---------------------------------------------------------------------------
# Phase 8, step 1 — compute_match_stats across the full scenario matrix
# ---------------------------------------------------------------------------

_SCENARIOS = [
    ("s1_clean_single_book_ou.json", "single-book O/U — 1 Betr, 1 DK → 100% match"),
    ("s2_multi_book_consensus.json", "multi-book consensus — DK+FD+ESPN at Betr line"),
    ("s3_milestone_devig_admission.json", "milestone ladder — 1 Betr, 2 DK rungs → matched"),
    # Known divergence: find_ev_opportunities matches Betr hits@0.5 ↔ DK total_bases@0.5
    # via the O05 cross-market borrow in _filter_sharp_props_by_match_context, but
    # compute_match_stats builds its ladder from the raw DK board (no borrow), so it
    # reports matched_keys=0 / betr_match_rate_pct=0.0 for this scenario.
    # TODO: fix compute_match_stats to apply the O05 borrow so diagnostics match engine.
    ("s4_o05_hits_total_bases_borrow.json", "o0.5 cross-market borrow — hits borrows total_bases"),
    ("s5_event_hour_doubleheader_split.json", "doubleheader split — 1 Betr, 2 DK hours"),
    ("s6_ambiguous_sharp_ladder_collision.json", "ambiguous collision — conflicting DK odds"),
    ("s7_live_vs_pregame_gate.json", "live/pregame gate — live Betr vs pregame DK"),
]


@pytest.mark.parametrize("filename,description", _SCENARIOS, ids=[s[0] for s in _SCENARIOS])
def test_match_stats_scenario_matrix(
    filename: str,
    description: str,
    snapshot: SnapshotAssertion,
) -> None:
    """Snapshot compute_match_stats for every Phase 1 scenario."""
    scenario = _load(filename)
    stats = compute_match_stats(
        scenario["betr_props"],
        scenario["dk_props"],
        fanduel_props=scenario.get("fd_props"),
        espn_props=scenario.get("espn_props"),
    )
    assert _clean_stats(stats) == snapshot


# ---------------------------------------------------------------------------
# Phase 8, step 2 — team-abbreviation canon golden
# ---------------------------------------------------------------------------


def test_team_abbrev_mismatch_still_matches() -> None:
    """DK 'CWS@NYY' vs Betr 'CHW@NYY': match key ignores game → opportunity produced."""
    betr = [
        {
            "sportsbook": "Betr",
            "player": "Luis Robert Jr.",
            "market": "hits",
            "line": 0.5,
            "over_odds": -160,
            "under_odds": 130,
            "league": "MLB",
            "game": "CHW@NYY",
            "event_start": _EVENT_START_A,
        }
    ]
    dk = [
        {
            "sportsbook": "DraftKings",
            "player": "Luis Robert Jr.",
            "market": "hits",
            "line": 0.5,
            "over_odds": -170,
            "under_odds": 140,
            "is_main_line": True,
            "league": "MLB",
            "game": "CWS@NYY",
            "event_start": _EVENT_START_B,
        }
    ]
    rows = find_ev_opportunities(betr, dk)
    assert rows, "expected a match despite differing team abbreviations"
    assert rows[0]["game"] == "CHW@NYY", (
        f"game should be canonical Betr form 'CHW@NYY', got {rows[0]['game']!r}"
    )


def test_team_abbrev_mismatch_match_stats_golden(snapshot: SnapshotAssertion) -> None:
    """compute_match_stats with differing team abbrevs — must count as matched."""
    betr = [
        {
            "sportsbook": "Betr",
            "player": "Luis Robert Jr.",
            "market": "hits",
            "line": 0.5,
            "over_odds": -160,
            "under_odds": 130,
            "league": "MLB",
            "game": "CHW@NYY",
            "event_start": _EVENT_START_A,
        }
    ]
    dk = [
        {
            "sportsbook": "DraftKings",
            "player": "Luis Robert Jr.",
            "market": "hits",
            "line": 0.5,
            "over_odds": -170,
            "under_odds": 140,
            "is_main_line": True,
            "league": "MLB",
            "game": "CWS@NYY",
            "event_start": _EVENT_START_B,
        }
    ]
    stats = compute_match_stats(betr, dk)
    assert _clean_stats(stats) == snapshot
    assert stats["matched_keys"] == 1, (
        "team-abbrev mismatch should not break matching (game is not in match key)"
    )
    assert stats["betr_match_rate_pct"] == 100.0
