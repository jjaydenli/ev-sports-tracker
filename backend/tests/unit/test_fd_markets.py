import pytest

from config.fd_markets import (
    FD_DEFAULT_SCRAPE_MARKETS,
    FD_MLB_DEFAULT_SCRAPE_MARKETS,
    FD_MLB_MILESTONE_MARKETS,
    canonical_to_tab_for_league,
    default_scrape_markets_for_league,
    is_core_ou_market,
    milestone_markets_for_league,
    milestone_threshold_to_line,
    parse_player_milestone_market_type,
    parse_player_ou_market_type,
    tab_for_canonical_market,
)
from scrapers.sportsbooks.fd_engine import scrape_targets_for_markets


def test_nba_default_scrape_markets_unchanged():
    assert default_scrape_markets_for_league("nba") == FD_DEFAULT_SCRAPE_MARKETS


def test_nba_parse_player_ou_market_type():
    assert parse_player_ou_market_type("PLAYER_A_TOTAL_POINTS", league="nba") == (
        "points",
        False,
    )
    assert parse_player_ou_market_type("PLAYER_H_ALT_TOTAL_REBOUNDS", league="nba") == (
        "rebounds",
        True,
    )


def test_mlb_parse_pitcher_strikeouts_market_type():
    assert parse_player_ou_market_type(
        "PITCHER_C_TOTAL_STRIKEOUTS", league="mlb"
    ) == ("pitching_strikeouts", False)
    assert parse_player_ou_market_type(
        "PITCHER_E_TOTAL_STRIKEOUTS", league="mlb"
    ) == ("pitching_strikeouts", False)
    assert parse_player_ou_market_type("PITCHER_C_STRIKEOUTS", league="mlb") is None
    assert parse_player_ou_market_type("TO_RECORD_2+_HITS", league="mlb") is None


def test_mlb_parse_player_milestone_market_type():
    assert parse_player_milestone_market_type(
        "TO_RECORD_2+_TOTAL_BASES", league="mlb"
    ) == ("total_bases", 2)
    assert parse_player_milestone_market_type(
        "TO_RECORD_3+_TOTAL_BASES", league="mlb"
    ) == ("total_bases", 3)
    assert parse_player_milestone_market_type(
        "PLAYER_TO_RECORD_A_HIT", league="mlb"
    ) == ("hits", 1)
    assert parse_player_milestone_market_type(
        "PLAYER_TO_RECORD_2+_HITS", league="mlb"
    ) == ("hits", 2)
    assert parse_player_milestone_market_type(
        "TO_RECORD_A_RUN", league="mlb"
    ) == ("runs", 1)
    assert parse_player_milestone_market_type(
        "TO_RECORD_AN_RBI", league="mlb"
    ) == ("rbi", 1)
    assert parse_player_milestone_market_type(
        "PLAYER_TO_RECORD_1+_HITS+RUNS+RBIS", league="mlb"
    ) == ("h+r+rbi", 1)
    assert parse_player_milestone_market_type(
        "TO_RECORD_A_STOLEN_BASE", league="mlb"
    ) is None
    assert parse_player_milestone_market_type(
        "PITCHER_C_TOTAL_STRIKEOUTS", league="mlb"
    ) is None


@pytest.mark.parametrize(
    "market_type, market_name, expected",
    [
        # marketType -> marketName pairs from the 2026-11-01 live NBA captures
        # (event 36257605); the expected value is read off FanDuel's display name.
        ("TO_SCORE_15+_POINTS", "15+ Points", ("points", 15)),
        ("TO_RECORD_8+_REBOUNDS", "8+ Rebounds", ("rebounds", 8)),
        ("TO_RECORD_10+_ASSISTS", "10+ Assists", ("assists", 10)),
        ("2+_MADE_THREES", "2+ Threes", ("threes", 2)),
        ("TO_RECORD_25+_PTS_+_REB", "25+ Pts + Reb", ("pts+reb", 25)),
        ("TO_RECORD_35+_PTS_+_AST", "35+ Pts + Ast", ("pts+ast", 35)),
        ("TO_RECORD_10+_REB_+_AST", "10+ Reb + Ast", ("reb+ast", 10)),
        ("TO_RECORD_30+_PTS_+_REB_+_AST", "30+ Pts + Reb + Ast", ("pra", 30)),
    ],
)
def test_nba_parse_player_milestone_market_type(market_type, market_name, expected):
    assert (
        parse_player_milestone_market_type(market_type, league="nba") == expected
    ), market_name


@pytest.mark.parametrize(
    "market_type",
    [
        "TO_RECORD_A_DOUBLE_DOUBLE",
        "TO_RECORD_A_TRIPLE_DOUBLE",
        "TO_RECORD_2+_STEALS",
        "TO_RECORD_2+_BLOCKS",
        "3RD_QUARTER_TOTAL_POINTS",
        "PLAYER_F_TOTAL_ASSISTS",
        "MONEY_LINE",
    ],
)
def test_nba_parse_player_milestone_market_type_rejects_unmapped(market_type):
    assert parse_player_milestone_market_type(market_type, league="nba") is None


def test_milestone_threshold_to_line():
    assert milestone_threshold_to_line(1) == 0.5
    assert milestone_threshold_to_line(3) == 2.5


def test_mlb_milestone_markets_registry():
    assert "total_bases" in FD_MLB_MILESTONE_MARKETS
    assert milestone_markets_for_league("nba") == ()


def test_mlb_tab_for_strikeouts():
    assert tab_for_canonical_market("pitching_strikeouts", league="mlb") == "pitcher-props"
    assert tab_for_canonical_market("hits", league="mlb") == "batter-props"


def test_mlb_default_scrape_includes_all_configured_markets():
    assert "pitching_strikeouts" in FD_MLB_DEFAULT_SCRAPE_MARKETS
    assert "hits" in FD_MLB_DEFAULT_SCRAPE_MARKETS
    assert len(FD_MLB_DEFAULT_SCRAPE_MARKETS) == 13


def test_mlb_scrape_targets_groups_pitcher_markets_on_one_tab():
    targets = scrape_targets_for_markets(
        ["pitching_strikeouts", "hits_allowed", "earned_runs"], league="mlb"
    )
    assert ("pitcher-props", {"pitching_strikeouts", "hits_allowed", "earned_runs"}) in targets


def test_nba_scrape_targets_unchanged():
    assert scrape_targets_for_markets(["points"], league="nba") == [
        ("player-points", {"points"})
    ]
    assert scrape_targets_for_markets(["threes", "pra"], league="nba") == [
        ("same-game-parlay-", {"threes", "pra"}),
    ]


def test_is_core_ou_market_per_league():
    assert is_core_ou_market("points", league="nba")
    assert not is_core_ou_market("pitching_strikeouts", league="nba")
    assert is_core_ou_market("pitching_strikeouts", league="mlb")
    assert is_core_ou_market("hits", league="mlb")


def test_canonical_to_tab_nba_matches_legacy():
    nba = canonical_to_tab_for_league("nba")
    assert nba["points"] == "player-points"
    assert nba["rebounds"] == "player-rebounds"
