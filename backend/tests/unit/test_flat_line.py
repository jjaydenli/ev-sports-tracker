from core.engine import find_ev_opportunities
from core.flat_line import (
    adjusted_breakeven_probability,
    is_flat_line,
    line_kind,
    push_probability,
)

_EVENT_START = "2026-06-19T23:00:00.000Z"


def test_is_flat_line_detects_integers():
    assert is_flat_line(4.0)
    assert not is_flat_line(4.5)
    assert line_kind(4.0) == "flat"
    assert line_kind(4.5) == "half_point"


def test_adjusted_breakeven_raises_required_win_prob():
    base = 0.5454545
    adjusted = adjusted_breakeven_probability(base, "rebounds")
    assert adjusted > base
    assert push_probability("rebounds") > 0


def test_find_ev_skips_flat_lines_by_default():
    betr = [
        {
            "sportsbook": "Betr",
            "player": "Player A",
            "market": "rebounds",
            "line": 4.0,
            "line_kind": "flat",
            "over_odds": -120,
            "under_odds": -120,
        }
    ]
    dk = [
        {
            "sportsbook": "DraftKings",
            "player": "Player A",
            "market": "rebounds",
            "line": 4.5,
            "over_odds": -110,
            "under_odds": -110,
            "is_main_line": True,
        }
    ]

    assert find_ev_opportunities(betr, dk) == []


def test_find_ev_includes_flat_lines_when_flag_set():
    betr = [
        {
            "sportsbook": "Betr",
            "player": "Player A",
            "market": "rebounds",
            "line": 4.0,
            "line_kind": "flat",
            "over_odds": -120,
            "under_odds": -120,
            "event_start": _EVENT_START,
        }
    ]
    dk = [
        {
            "sportsbook": "DraftKings",
            "player": "Player A",
            "market": "rebounds",
            "line": 4.0,
            "over_odds": -140,
            "under_odds": 120,
            "is_main_line": True,
            "event_start": _EVENT_START,
        }
    ]

    results = find_ev_opportunities(betr, dk, include_flat_lines=True)

    assert results
    assert results[0]["line_kind"] == "flat"
