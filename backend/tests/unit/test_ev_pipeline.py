import json

from core.ev_pipeline import run_ev_scan

_EVENT_START = "2026-06-19T23:00:00.000Z"


def test_run_ev_scan_writes_opportunities(tmp_path):
    betr_board = [
        {
            "sportsbook": "Betr",
            "player": "Test Player",
            "market": "points",
            "line": 20.5,
            "prop_type": "standard",
            "over_odds": -120,
            "under_odds": -120,
            "event_start": _EVENT_START,
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
            "event_start": _EVENT_START,
        }
    ]

    (tmp_path / "betr_normalized.json").write_text(
        json.dumps(betr_board), encoding="utf-8"
    )
    (tmp_path / "dk_normalized.json").write_text(json.dumps(dk_board), encoding="utf-8")

    opportunities = run_ev_scan(tmp_path, normalize_first=False)

    assert opportunities
    assert (tmp_path / "ev_opportunities.json").exists()
    assert opportunities[0]["side"] == "over"
    assert "side_hit_pct" in opportunities[0]
    assert "plus_ev" in opportunities[0]
    assert len(opportunities) <= 15
