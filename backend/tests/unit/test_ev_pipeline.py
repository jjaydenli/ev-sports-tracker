import json

import pytest
from loguru import logger

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


def _prop(sportsbook: str, player: str, over: int, under: int) -> dict:
    return {
        "sportsbook": sportsbook,
        "player": player,
        "market": "points",
        "line": 20.5,
        "prop_type": "standard",
        "over_odds": over,
        "under_odds": under,
        "event_start": _EVENT_START,
    }


@pytest.mark.parametrize(
    ("dk_player", "min_ev", "expected_reason"),
    [
        ("Someone Else", None, "none of 1 betr props resolved to an EV-eligible sharp line"),
        # Matched at EV +0.0166 (hand oracle in test_ev_engine), so 0.5 filters it out.
        ("Test Player", 0.5, "nothing reached min_ev=0.5"),
    ],
    ids=["no_match", "below_min_ev"],
)
def test_run_ev_scan_empty_board_says_why(tmp_path, dk_player, min_ev, expected_reason):
    """An empty board is a warning with a reason, not a bare top=0 success line."""
    (tmp_path / "betr_normalized.json").write_text(
        json.dumps([_prop("Betr", "Test Player", -120, -120)]), encoding="utf-8"
    )
    (tmp_path / "dk_normalized.json").write_text(
        json.dumps([_prop("DraftKings", dk_player, -140, 120)]), encoding="utf-8"
    )
    records: list = []
    sink_id = logger.add(lambda message: records.append(message.record), level="INFO")
    try:
        opportunities = run_ev_scan(tmp_path, normalize_first=False, min_ev=min_ev)
    finally:
        logger.remove(sink_id)

    assert opportunities == []
    warnings = [r["message"] for r in records if r["level"].name == "WARNING"]
    assert any(expected_reason in message for message in warnings), warnings
    assert not any(r["level"].name == "SUCCESS" for r in records)
