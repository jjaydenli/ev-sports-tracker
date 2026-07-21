import json

import pytest

from core.ev_pipeline import run_ev_scan
from core.ev_run_diff import (
    EV_DIFF_FILENAME,
    EV_PREVIOUS_FILENAME,
    build_opportunity_row_id,
    compute_run_diff,
    format_run_diff_summary,
    rotate_ev_opportunities_file,
)
from core.pipeline_artifacts import load_wrapped_board


def _opp(
    player: str,
    market: str,
    line: float,
    side: str,
    ev: float,
    ev_pct: float,
) -> dict:
    return {
        "player": player,
        "market": market,
        "line": line,
        "side": side,
        "ev": ev,
        "ev_pct": ev_pct,
        "side_hit_pct": 55.0,
        "dk_over_odds": -110,
        "dk_under_odds": -110,
    }


def test_build_opportunity_row_id_normalizes_player_casing():
    lower = build_opportunity_row_id(
        _opp("shai gilgeous-alexander", "points", 29.5, "over", 0.1, 10.0)
    )
    mixed = build_opportunity_row_id(
        _opp("Shai Gilgeous-Alexander", "points", 29.5, "over", 0.1, 10.0)
    )
    assert lower == mixed == "shai gilgeous-alexander|points|29.5|over"


def test_compute_run_diff_buckets():
    previous = [
        _opp("A", "points", 20.5, "over", 0.05, 5.0),
        _opp("B", "rebounds", 5.5, "under", 0.03, 3.0),
        _opp("C", "assists", 7.5, "over", 0.02, 2.0),
    ]
    current = [
        _opp("A", "points", 20.5, "over", 0.08, 8.0),
        _opp("B", "rebounds", 5.5, "under", 0.01, 1.0),
        _opp("D", "threes", 2.5, "over", 0.04, 4.0),
    ]

    diff = compute_run_diff(previous, current)

    assert diff["has_previous"] is True
    assert {row["id"] for row in diff["new"]} == {"d|threes|2.5|over"}
    assert {row["id"] for row in diff["removed"]} == {"c|assists|7.5|over"}
    assert len(diff["improved"]) == 1
    assert diff["improved"][0]["id"] == "a|points|20.5|over"
    assert diff["improved"][0]["ev_delta"] == pytest.approx(0.03)
    assert len(diff["fell"]) == 1
    assert diff["fell"][0]["id"] == "b|rebounds|5.5|under"


def test_compute_run_diff_ignores_unchanged_ev():
    row = _opp("A", "points", 20.5, "over", 0.05, 5.0)
    diff = compute_run_diff([row], [dict(row)])
    assert diff["new"] == []
    assert diff["removed"] == []
    assert diff["improved"] == []
    assert diff["fell"] == []


def test_format_run_diff_summary_includes_sections():
    diff = compute_run_diff(
        [_opp("A", "points", 20.5, "over", 0.05, 5.0)],
        [_opp("B", "points", 21.5, "over", 0.06, 6.0)],
    )
    text = format_run_diff_summary(diff)
    assert "run diff" in text
    assert "NEW" in text
    assert "RM" in text


def test_rotate_ev_opportunities_file(tmp_path):
    current = tmp_path / "ev_opportunities.json"
    current.write_text(json.dumps([{"player": "X"}]), encoding="utf-8")

    rows, prior_id = rotate_ev_opportunities_file(tmp_path)

    assert rows == [{"player": "X"}]
    assert prior_id is None
    assert not current.exists()
    assert (tmp_path / EV_PREVIOUS_FILENAME).exists()


def test_run_ev_scan_writes_diff_on_second_run(tmp_path):
    event_start = "2026-06-19T23:00:00.000Z"
    betr_board = [
        {
            "sportsbook": "Betr",
            "player": "Test Player",
            "market": "points",
            "line": 20.5,
            "prop_type": "standard",
            "over_odds": -120,
            "under_odds": -120,
            "event_start": event_start,
        }
    ]
    dk_board = [
        {
            "sportsbook": "DraftKings",
            "player": "Test Player",
            "market": "points",
            "line": 20.5,
            "over_odds": -140,
            "under_odds": 120,
            "event_start": event_start,
        }
    ]

    (tmp_path / "betr_normalized.json").write_text(
        json.dumps(betr_board), encoding="utf-8"
    )
    (tmp_path / "dk_normalized.json").write_text(
        json.dumps(dk_board), encoding="utf-8"
    )

    first = run_ev_scan(tmp_path, normalize_first=False)
    assert first
    assert (tmp_path / "ev_opportunities.json").exists()
    assert not (tmp_path / EV_PREVIOUS_FILENAME).exists()
    assert not (tmp_path / EV_DIFF_FILENAME).exists()

    second = run_ev_scan(tmp_path, normalize_first=False)
    assert second
    assert (tmp_path / EV_PREVIOUS_FILENAME).exists()
    assert (tmp_path / EV_DIFF_FILENAME).exists()
    _, current_opps = load_wrapped_board(tmp_path / "ev_opportunities.json")
    assert isinstance(current_opps, list)

    diff_payload = json.loads((tmp_path / EV_DIFF_FILENAME).read_text(encoding="utf-8"))
    assert diff_payload["has_previous"] is True
    assert "generated_at" in diff_payload
