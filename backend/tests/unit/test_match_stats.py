import json

from core.engine import (
    compute_match_stats,
    list_unmatched_betr_props,
    list_unmatched_dk_props,
)
from core.ev_pipeline import persist_match_diagnostics


def test_compute_match_stats_counts_cross_book_matches():
    betr = [
        {
            "player": "Test Player",
            "market": "points",
            "line": 20.5,
            "over_odds": -120,
            "under_odds": -120,
        },
        {
            "player": "No Match",
            "market": "assists",
            "line": 5.5,
            "over_odds": -120,
            "under_odds": -120,
        },
    ]
    dk = [
        {
            "player": "Test Player",
            "market": "points",
            "line": 20.5,
            "over_odds": -110,
            "under_odds": -110,
        },
        {
            "player": "DK Only",
            "market": "rebounds",
            "line": 8.5,
            "over_odds": -110,
            "under_odds": -110,
        },
    ]

    stats = compute_match_stats(betr, dk)

    assert stats["betr_props"] == 2
    assert stats["dk_props"] == 2
    assert stats["matched_keys"] == 1
    assert stats["unmatched_betr"] == 1
    assert stats["unmatched_betr_no_dk_market"] == 1
    assert stats["unmatched_betr_dk_missing_odds"] == 0
    assert stats["unmatched_dk"] == 1
    assert stats["betr_match_rate_pct"] == 50.0


def test_list_unmatched_betr_includes_reason_and_key():
    betr = [
        {
            "player": "No Match",
            "market": "assists",
            "line": 5.5,
            "over_odds": -120,
            "under_odds": -120,
        },
    ]
    dk: list[dict] = []

    unmatched = list_unmatched_betr_props(betr, dk)

    assert len(unmatched) == 1
    assert unmatched[0]["reason"] == "no_dk_market"
    assert unmatched[0]["dk_lines_available"] == []
    assert unmatched[0]["match_key"] == "no match|assists|5.5"


def test_list_unmatched_dk_flags_no_betr_line():
    betr: list[dict] = []
    dk = [
        {
            "player": "DK Only",
            "market": "points",
            "line": 10.5,
            "over_odds": -110,
            "under_odds": -110,
        },
    ]

    unmatched = list_unmatched_dk_props(betr, dk)

    assert len(unmatched) == 1
    assert unmatched[0]["reason"] == "no_betr_line"


def test_compute_match_stats_no_bracket_counts_as_no_dk_bracket():
    """A single-sided anchor (no bracketing pair) can't interpolate — counts as unbracketed, not matched."""
    betr = [
        {
            "player": "Shai Gilgeous-Alexander",
            "market": "points",
            "line": 28.5,
            "over_odds": -120,
            "under_odds": -120,
        },
    ]
    dk = [
        {
            "player": "Shai Gilgeous-Alexander",
            "market": "points",
            "line": 29.5,
            "over_odds": -145,
            "under_odds": 110,
            "is_main_line": True,
        },
    ]

    stats = compute_match_stats(betr, dk)

    assert stats["matched_keys"] == 0
    assert stats["unmatched_betr"] == 1
    assert stats["unmatched_betr_no_dk_bracket"] == 1
    assert stats["unmatched_betr_no_exact_sharp_line"] == 0


def test_compute_match_stats_interpolated_line_counts_as_matched():
    betr = [
        {
            "player": "Test Player",
            "market": "points",
            "line": 28.5,
            "over_odds": -120,
            "under_odds": -120,
        },
    ]
    dk = [
        {
            "player": "Test Player",
            "market": "points",
            "line": 27.5,
            "over_odds": -130,
            "under_odds": 100,
            "is_main_line": False,
        },
        {
            "player": "Test Player",
            "market": "points",
            "line": 29.5,
            "over_odds": -145,
            "under_odds": 110,
            "is_main_line": True,
        },
    ]

    stats = compute_match_stats(betr, dk)

    assert stats["matched_keys"] == 1
    assert stats["unmatched_betr_no_exact_sharp_line"] == 0


def test_persist_match_diagnostics_writes_report_files(tmp_path):
    betr = [
        {
            "player": "Test Player",
            "market": "points",
            "line": 20.5,
            "over_odds": -120,
            "under_odds": -120,
        },
    ]
    dk = [
        {
            "player": "Test Player",
            "market": "points",
            "line": 20.5,
            "over_odds": -110,
            "under_odds": -110,
        },
        {
            "player": "DK Only",
            "market": "rebounds",
            "line": 8.5,
            "over_odds": -110,
            "under_odds": -110,
        },
    ]

    stats = persist_match_diagnostics(tmp_path, betr, dk)

    assert stats["matched_keys"] == 1
    report = json.loads((tmp_path / "match_report.json").read_text(encoding="utf-8"))
    assert report["matched_keys"] == 1
    assert "generated_at" in report
    assert (tmp_path / "unmatched_betr.json").exists()
    assert (tmp_path / "unmatched_dk.json").exists()


def test_compute_match_stats_espn_milestone_shifts_reason_from_no_market():
    """With ESPN milestone data the stats layer must find the market, not report no_dk_market."""
    betr = [
        {
            "player": "Jazz Chisholm Jr.",
            "market": "singles",
            "line": 0.5,
            "line_kind": "milestone",
            "over_odds": -160,
            "under_odds": 130,
        }
    ]
    espn_heavy_over = [
        {
            "sportsbook": "ESPN",
            "player": "Jazz Chisholm Jr.",
            "market": "singles",
            "line": 0.5,
            "line_kind": "milestone",
            "over_odds": -175,
            "under_odds": None,
            "is_main_line": True,
            "milestone_threshold": 1,
            "league": "MLB",
        }
    ]

    stats_without_espn = compute_match_stats(betr, [])
    stats_with_espn = compute_match_stats(betr, [], espn_props=espn_heavy_over)

    # Without ESPN: no sharp market known → no_dk_market
    assert stats_without_espn["unmatched_betr_no_dk_market"] == 1

    # With ESPN milestone (over-admitted): market discovered, reason shifts away from no_dk_market
    assert stats_with_espn["unmatched_betr_no_dk_market"] == 0, (
        "_build_match_ladders must include ESPN milestone props so betr_unmatched_reason "
        "finds the market rather than reporting no_dk_market"
    )


def test_compute_match_stats_espn_milestone_under_admitted_counts_as_matched():
    """ESPN milestone over at +110 (under-admitted) lets Betr under be evaluated as matched."""
    betr = [
        {
            "player": "Jazz Chisholm Jr.",
            "market": "singles",
            "line": 0.5,
            "line_kind": "milestone",
            "over_odds": -160,
            "under_odds": 130,
        }
    ]
    # ESPN prices the over as a moderate underdog — fair_over < 0.5 → admitted_under=True
    espn_light_over = [
        {
            "sportsbook": "ESPN",
            "player": "Jazz Chisholm Jr.",
            "market": "singles",
            "line": 0.5,
            "line_kind": "milestone",
            "over_odds": 110,
            "under_odds": None,
            "is_main_line": True,
            "milestone_threshold": 1,
            "league": "MLB",
        }
    ]

    stats = compute_match_stats(betr, [], espn_props=espn_light_over)

    assert stats["matched_keys"] == 1, (
        "ESPN milestone over at +110 (fair_over < 0.5) should admit the under side "
        "and allow the Betr under to be evaluated as matched"
    )
    assert stats["unmatched_betr"] == 0
