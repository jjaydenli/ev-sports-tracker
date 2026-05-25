import pytest

from core.engine import (
    _favored_no_vig,
    build_prop_key,
    compare_betr_vs_draftkings,
    find_ev_opportunities,
    normalize_player_name,
)
from utils.math_utils import american_to_implied, BETR_STANDARD_BREAKEVEN_ODDS


def _betr_prop(
    player: str,
    market: str,
    line: float,
    *,
    over_odds: int | None = -120,
    under_odds: int | None = -120,
) -> dict:
    return {
        "sportsbook": "Betr",
        "player": player,
        "market": market,
        "line": line,
        "prop_type": "standard",
        "over_odds": over_odds,
        "under_odds": under_odds,
    }


def _dk_prop(player: str, market: str, line: float, over: int, under: int) -> dict:
    return {
        "sportsbook": "DraftKings",
        "player": player,
        "market": market,
        "line": line,
        "over_odds": over,
        "under_odds": under,
    }


def test_favored_no_vig_picks_higher_probability_side():
    side, prob = _favored_no_vig(0.48, 0.52)
    assert side == "under"
    assert prob == 0.52


def test_build_prop_key_normalizes_player_casing():
    lower = build_prop_key(_betr_prop("shai gilgeous-alexander", "points", 29.5))
    mixed = build_prop_key(_betr_prop("Shai Gilgeous-Alexander", "points", 29.5))

    assert lower == mixed
    assert normalize_player_name("  Shai   Gilgeous-Alexander ") == "shai gilgeous-alexander"


def test_find_ev_opportunities_returns_empty_when_no_match():
    betr = [_betr_prop("Player A", "points", 10.5)]
    dk = [_dk_prop("Player B", "points", 10.5, -110, -110)]

    assert find_ev_opportunities(betr, dk) == []


def test_find_ev_opportunities_finds_positive_ev_over():
    betr = [_betr_prop("Test Player", "points", 20.5)]
    dk = [_dk_prop("Test Player", "points", 20.5, -140, 120)]

    results = find_ev_opportunities(betr, dk, min_ev=0.0)

    over_plays = [row for row in results if row["side"] == "over"]
    assert over_plays
    assert over_plays[0]["ev"] > 0
    assert over_plays[0]["player"] == "Test Player"
    assert over_plays[0]["dk_over_odds"] == -140
    assert over_plays[0]["dk_under_odds"] == 120
    assert over_plays[0]["no_vig_favored_side"] == "over"
    assert over_plays[0]["no_vig_implied_pct"] > over_plays[0]["betr_implied_pct"]
    assert "dk_over_implied_pct" not in over_plays[0]


def test_find_ev_opportunities_respects_min_ev_threshold():
    betr = [_betr_prop("Test Player", "points", 20.5)]
    dk = [_dk_prop("Test Player", "points", 20.5, -140, 120)]

    all_results = find_ev_opportunities(betr, dk, min_ev=0.0)
    assert all_results
    assert find_ev_opportunities(betr, dk, min_ev=0.5) == []


def test_even_sharp_line_has_no_ev_at_minus_120_breakeven():
    betr = [_betr_prop("Test Player", "points", 20.5)]
    dk = [_dk_prop("Test Player", "points", 20.5, -110, -110)]

    assert find_ev_opportunities(betr, dk, min_ev=0.0) == []


def test_compare_betr_vs_draftkings_sorts_by_ev_descending():
    betr = [
        _betr_prop("Player A", "points", 10.5),
        _betr_prop("Player B", "rebounds", 5.5),
    ]
    dk = [
        _dk_prop("Player A", "points", 10.5, -140, 120),
        _dk_prop("Player B", "rebounds", 5.5, 120, -140),
    ]

    results = compare_betr_vs_draftkings(betr, dk)

    assert len(results) >= 2
    assert results[0]["ev"] >= results[-1]["ev"]


def test_breakeven_probability_matches_betr_standard_odds():
    assert BETR_STANDARD_BREAKEVEN_ODDS == -120
    assert american_to_implied(BETR_STANDARD_BREAKEVEN_ODDS) == pytest.approx(
        0.5454545, rel=1e-4
    )


def test_find_ev_opportunities_skips_blocked_under_side():
    """Do not emit under +EV when Betr only allows the over (under_odds=None)."""
    betr = [_betr_prop("Dean Wade", "rebounds", 3.5, over_odds=-120, under_odds=None)]
    dk = [_dk_prop("Dean Wade", "rebounds", 3.5, 111, -147)]

    results = find_ev_opportunities(betr, dk, min_ev=0.0)

    assert all(row["side"] != "under" for row in results)
