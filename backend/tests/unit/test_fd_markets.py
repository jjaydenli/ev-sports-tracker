from config.fd_markets import (
    FD_DEFAULT_SCRAPE_MARKETS,
    FD_MLB_DEFAULT_SCRAPE_MARKETS,
    canonical_to_tab_for_league,
    default_scrape_markets_for_league,
    is_core_ou_market,
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
