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
    event_start: str = "2026-06-19T23:00:00.000Z",
) -> dict:
    return {
        "sportsbook": "Betr",
        "player": player,
        "market": market,
        "line": line,
        "prop_type": "standard",
        "over_odds": over_odds,
        "under_odds": under_odds,
        "event_start": event_start,
    }


def _dk_prop(
    player: str,
    market: str,
    line: float,
    over: int,
    under: int,
    *,
    event_start: str = "2026-06-19T23:00:00.000Z",
) -> dict:
    return {
        "sportsbook": "DraftKings",
        "player": player,
        "market": market,
        "line": line,
        "over_odds": over,
        "under_odds": under,
        "event_start": event_start,
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


def test_build_prop_key_includes_league_when_present():
    base = _betr_prop("Aaron Judge", "hits", 1.5)
    base["league"] = "MLB"
    assert build_prop_key(base) == "aaron judge|hits|1.5|MLB"


def test_find_ev_opportunities_returns_empty_when_no_match():
    betr = [_betr_prop("Player A", "points", 10.5)]
    dk = [_dk_prop("Player B", "points", 10.5, -110, -110)]

    assert find_ev_opportunities(betr, dk) == []


def test_find_ev_opportunities_includes_league_from_dfs_prop():
    betr = _betr_prop("Aaron Judge", "hits", 1.5)
    betr["league"] = "MLB"
    dk = [_dk_prop("Aaron Judge", "hits", 1.5, -115, -110)]
    dk[0]["league"] = "MLB"

    results = find_ev_opportunities([betr], dk, min_ev=0.0)

    assert results
    assert all(row["league"] == "MLB" for row in results)


def test_find_ev_opportunities_finds_positive_ev_over():
    betr = [_betr_prop("Test Player", "points", 20.5)]
    dk = [_dk_prop("Test Player", "points", 20.5, -140, 120)]

    results = find_ev_opportunities(betr, dk, min_ev=0.0)

    over_plays = [row for row in results if row["side"] == "over"]
    assert over_plays
    assert over_plays[0]["ev"] > 0
    assert over_plays[0]["plus_ev"] is True
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
    over_rows = [row for row in all_results if row["side"] == "over"]
    assert over_rows and over_rows[0]["plus_ev"]

    flagged_only = find_ev_opportunities(betr, dk, min_ev=0.5)
    assert flagged_only
    assert all(not row["plus_ev"] for row in flagged_only)

    filtered = find_ev_opportunities(betr, dk, min_ev=0.5, filter_min_ev=True)
    assert filtered == []


def test_filter_min_ev_keeps_plus_ev_rows():
    betr = [_betr_prop("Test Player", "points", 20.5)]
    dk = [_dk_prop("Test Player", "points", 20.5, -140, 120)]

    results = find_ev_opportunities(betr, dk, min_ev=0.01, filter_min_ev=True, top_n=15)

    assert results
    assert all(row["plus_ev"] for row in results)
    assert all(row["ev"] > 0.01 for row in results)


def test_even_sharp_line_negative_ev_at_minus_120_breakeven():
    """50/50 de-vig vs -120 breakeven (54.55%) is -EV on both sides."""
    betr = [_betr_prop("Test Player", "points", 20.5)]
    dk = [_dk_prop("Test Player", "points", 20.5, -110, -110)]

    results = find_ev_opportunities(betr, dk, min_ev=0.0)
    assert len(results) == 2
    assert all(row["ev"] == pytest.approx(-0.0455, abs=1e-4) for row in results)
    assert all(not row["plus_ev"] for row in results)


def test_find_ev_opportunities_top_n_limits_results():
    betr = [
        _betr_prop("Player A", "points", 10.5),
        _betr_prop("Player B", "rebounds", 5.5),
        _betr_prop("Player C", "assists", 3.5),
    ]
    dk = [
        _dk_prop("Player A", "points", 10.5, -140, 120),
        _dk_prop("Player B", "rebounds", 5.5, 120, -140),
        _dk_prop("Player C", "assists", 3.5, -110, -110),
    ]

    results = find_ev_opportunities(betr, dk, top_n=2)

    assert len(results) == 2
    assert results[0]["ev"] >= results[1]["ev"]


def test_negative_ev_row_included_with_plus_ev_false():
    betr = [_betr_prop("Test Player", "points", 20.5)]
    dk = [_dk_prop("Test Player", "points", 20.5, 120, -140)]

    results = find_ev_opportunities(betr, dk, min_ev=0.0, top_n=15)

    assert results
    assert any(row["ev"] < 0 and not row["plus_ev"] for row in results)


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

    assert results, "over-side opportunity should still be produced when under_odds=None"
    assert all(row["side"] != "under" for row in results)


def test_ev_row_is_live_false_by_default():
    betr = [_betr_prop("Test Player", "points", 20.5)]
    dk = [_dk_prop("Test Player", "points", 20.5, -140, 120)]

    results = find_ev_opportunities(betr, dk)

    assert results
    assert all(row["is_live"] is False for row in results)


def test_ev_row_is_live_true_when_dfs_prop_is_live():
    betr_live = {
        **_betr_prop("Test Player", "hits", 1.5),
        "game": "CIN@NYY",
        "is_live": True,
    }
    dk = [
        {
            **_dk_prop("Test Player", "hits", 1.5, -110, -110),
            "game": "CIN@NYY",
            "is_live": True,
        }
    ]

    results = find_ev_opportunities([betr_live], dk)

    assert results
    assert all(row["is_live"] is True for row in results)


def test_live_betr_ignores_pregame_sharp_same_matchup():
    """Live DFS rows must not pick up tomorrow's pregame sharp lines for the same teams."""
    betr_live = {
        **_betr_prop("Nathaniel Lowe", "hits", 0.5),
        "league": "MLB",
        "game": "CIN@NYY",
        "is_live": True,
    }
    dk_pregame = {
        **_dk_prop("Nathaniel Lowe", "hits", 0.5, -176, 132),
        "league": "MLB",
        "game": "CIN@NYY",
    }
    fd_pregame_milestone = {
        "sportsbook": "FanDuel",
        "player": "Nathaniel Lowe",
        "market": "hits",
        "line": 0.5,
        "line_kind": "milestone",
        "over_odds": -160,
        "game": "CIN@NYY",
        "league": "MLB",
    }

    results = find_ev_opportunities(
        [betr_live],
        [dk_pregame],
        fanduel_props=[fd_pregame_milestone],
        min_ev=0.0,
    )

    assert results == []


def test_pregame_betr_matches_pregame_sharp_with_game_scope():
    betr = {
        **_betr_prop("Nathaniel Lowe", "hits", 0.5),
        "league": "MLB",
        "game": "CIN@NYY",
    }
    dk = {
        **_dk_prop("Nathaniel Lowe", "hits", 0.5, -176, 132),
        "league": "MLB",
        "game": "CIN@NYY",
    }

    results = find_ev_opportunities([betr], [dk], min_ev=0.0)

    assert results
    assert results[0]["dk_over_odds"] == -176


def test_find_ev_opportunities_filters_mismatched_event_start_hour():
    betr = _betr_prop("Test Player", "points", 20.5)
    betr["event_start"] = "2026-06-19T23:00:00.000Z"
    dk = _dk_prop("Test Player", "points", 20.5, -140, 120)
    dk["event_start"] = "2026-06-20T23:00:00.000Z"

    assert find_ev_opportunities([betr], [dk], min_ev=0.0) == []


def test_find_ev_opportunities_passes_matching_event_start_hour():
    betr = _betr_prop("Test Player", "points", 20.5)
    betr["event_start"] = "2026-06-19T23:05:00.000Z"
    dk = _dk_prop("Test Player", "points", 20.5, -140, 120)
    dk["event_start"] = "2026-06-19T23:10:00.000Z"

    results = find_ev_opportunities([betr], [dk], min_ev=0.0)
    assert results


def test_find_ev_opportunities_passes_doubleheader_game_one_same_hour():
    """Same-day doubleheader game 1: start times within the same hour pass."""
    betr = _betr_prop("Test Player", "hits", 1.5)
    betr["event_start"] = "2026-06-19T17:05:00.000Z"
    dk = _dk_prop("Test Player", "hits", 1.5, -110, -110)
    dk["event_start"] = "2026-06-19T17:40:00.000Z"

    results = find_ev_opportunities([betr], [dk], min_ev=0.0)
    assert results


def test_find_ev_opportunities_missing_event_start_pregame_fail_closed():
    """Pregame Betr without event_start must not match sharp lines (fail closed)."""
    betr = _betr_prop("Test Player", "points", 20.5)
    del betr["event_start"]
    dk = _dk_prop("Test Player", "points", 20.5, -140, 120)
    dk["event_start"] = "2026-06-20T23:00:00.000Z"

    assert find_ev_opportunities([betr], [dk], min_ev=0.0) == []


def test_find_ev_opportunities_filters_doubleheader_game_two_block():
    """DH game 1 Betr must not match game 2 DK lines (different event_hour)."""
    betr = _betr_prop("Test Player", "hits", 1.5)
    betr["event_start"] = "2026-06-19T17:05:00.000Z"
    betr["game"] = "CIN@NYY"
    dk = _dk_prop("Test Player", "hits", 1.5, -110, -110)
    dk["event_start"] = "2026-06-19T23:10:00.000Z"
    dk["game"] = "CIN@NYY"

    assert find_ev_opportunities([betr], [dk], min_ev=0.0) == []


def test_find_ev_opportunities_freeman_series_uses_matching_day_only():
    """Betr today resolves against same-day DK only, not tomorrow's duplicate game."""
    betr = _betr_prop("Freddie Freeman", "total_bases", 1.5)
    betr["game"] = "BAL@LAD"
    betr["event_start"] = "2026-06-20T02:10:00.000Z"
    dk_today = _dk_prop("Freddie Freeman", "total_bases", 1.5, -106, -125)
    dk_today["game"] = "BAL@LAD"
    dk_today["event_start"] = "2026-06-20T02:10:00.000Z"
    dk_tomorrow = _dk_prop("Freddie Freeman", "total_bases", 1.5, 134, -179)
    dk_tomorrow["game"] = "BAL@LAD"
    dk_tomorrow["event_start"] = "2026-06-21T02:10:00.000Z"

    results = find_ev_opportunities([betr], [dk_today, dk_tomorrow], min_ev=0.0)
    assert results
    assert results[0]["dk_over_odds"] == -106


def test_find_ev_opportunities_freeman_series_blocks_tomorrow_only():
    """When only tomorrow's sharp line exists, Betr today does not match."""
    betr = _betr_prop("Freddie Freeman", "total_bases", 1.5)
    betr["game"] = "BAL@LAD"
    betr["event_start"] = "2026-06-20T02:10:00.000Z"
    dk_tomorrow = _dk_prop("Freddie Freeman", "total_bases", 1.5, 134, -179)
    dk_tomorrow["game"] = "BAL@LAD"
    dk_tomorrow["event_start"] = "2026-06-21T02:10:00.000Z"

    assert find_ev_opportunities([betr], [dk_tomorrow], min_ev=0.0) == []


def test_find_ev_opportunities_multi_book_filters_mismatched_event_hour():
    """Betr today uses DK only when FD row is tomorrow at the same line."""
    betr = _betr_prop("Test Player", "points", 20.5)
    betr["event_start"] = "2026-06-19T23:05:00.000Z"
    dk = _dk_prop("Test Player", "points", 20.5, -140, 120)
    dk["event_start"] = "2026-06-19T23:10:00.000Z"
    fd = {
        "sportsbook": "FanDuel",
        "player": "Test Player",
        "market": "points",
        "line": 20.5,
        "over_odds": -130,
        "under_odds": 110,
        "event_start": "2026-06-20T23:10:00.000Z",
    }

    results = find_ev_opportunities([betr], [dk], fanduel_props=[fd], min_ev=0.0)
    assert results
    assert results[0]["dk_over_odds"] == -140
    assert results[0]["fd_over_odds"] is None


def test_find_ev_opportunities_filters_series_duplicate_game_different_start():
    """Last-wins ladder no longer matters: per-Betr filter keeps today's DK row."""
    betr = _betr_prop("Freddie Freeman", "total_bases", 1.5)
    betr["game"] = "BAL@LAD"
    betr["event_start"] = "2026-06-20T02:10:00.000Z"
    dk_today = _dk_prop("Freddie Freeman", "total_bases", 1.5, -106, -125)
    dk_today["game"] = "BAL@LAD"
    dk_today["event_start"] = "2026-06-20T02:10:00.000Z"
    dk_tomorrow = _dk_prop("Freddie Freeman", "total_bases", 1.5, 134, -179)
    dk_tomorrow["game"] = "BAL@LAD"
    dk_tomorrow["event_start"] = "2026-06-21T02:10:00.000Z"

    results = find_ev_opportunities([betr], [dk_today, dk_tomorrow], min_ev=0.0)
    assert results
    assert results[0]["dk_over_odds"] == -106
