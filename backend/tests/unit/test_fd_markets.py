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
    ) == ("strikeouts", False)
    assert parse_player_ou_market_type(
        "PITCHER_E_TOTAL_STRIKEOUTS", league="mlb"
    ) == ("strikeouts", False)
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
    assert parse_player_milestone_market_type(
        "TO_SCORE_25+_POINTS", league="nba"
    ) is None


def test_milestone_threshold_to_line():
    assert milestone_threshold_to_line(1) == 0.5
    assert milestone_threshold_to_line(3) == 2.5


def test_mlb_milestone_markets_registry():
    assert "total_bases" in FD_MLB_MILESTONE_MARKETS
    assert milestone_markets_for_league("nba") == ()


def test_mlb_tab_for_strikeouts():
    assert tab_for_canonical_market("strikeouts", league="mlb") == "pitcher-props"
    assert tab_for_canonical_market("hits", league="mlb") == "batter-props"


def test_mlb_default_scrape_includes_all_configured_markets():
    assert "strikeouts" in FD_MLB_DEFAULT_SCRAPE_MARKETS
    assert "hits" in FD_MLB_DEFAULT_SCRAPE_MARKETS
    assert len(FD_MLB_DEFAULT_SCRAPE_MARKETS) == 13


def test_mlb_scrape_targets_groups_pitcher_markets_on_one_tab():
    targets = scrape_targets_for_markets(
        ["strikeouts", "hits_allowed", "earned_runs"], league="mlb"
    )
    assert ("pitcher-props", {"strikeouts", "hits_allowed", "earned_runs"}) in targets


def test_nba_scrape_targets_unchanged():
    assert scrape_targets_for_markets(["points"], league="nba") == [
        ("player-points", {"points"})
    ]
    assert scrape_targets_for_markets(["threes", "pra"], league="nba") == [
        ("same-game-parlay-", {"threes", "pra"}),
    ]


def test_is_core_ou_market_per_league():
    assert is_core_ou_market("points", league="nba")
    assert not is_core_ou_market("strikeouts", league="nba")
    assert is_core_ou_market("strikeouts", league="mlb")
    assert is_core_ou_market("hits", league="mlb")


def test_canonical_to_tab_nba_matches_legacy():
    nba = canonical_to_tab_for_league("nba")
    assert nba["points"] == "player-points"
    assert nba["rebounds"] == "player-rebounds"
