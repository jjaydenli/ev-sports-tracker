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


def test_compute_match_stats_aligns_line_mismatch_via_adjustment():
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

    assert stats["matched_keys"] == 1
    assert stats["unmatched_betr"] == 0


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
