from config.espn_competitions import ESPN_LEAGUE_SLATES
from config.espn_markets import (
    ESPN_MLB_DEFAULT_SCRAPE_MARKETS,
    canonical_market_for_group_id,
    default_scrape_markets_for_league,
    is_ou_group_id,
    known_markets_for_league,
    prop_section_slugs_for_league,
)


def test_mlb_and_wnba_slates_registered():
    assert "mlb" in ESPN_LEAGUE_SLATES
    assert "wnba" in ESPN_LEAGUE_SLATES


def test_mlb_default_scrape_markets():
    assert default_scrape_markets_for_league("mlb") == ESPN_MLB_DEFAULT_SCRAPE_MARKETS
    assert "strikeouts" in known_markets_for_league("mlb")


def test_mlb_prop_section_slugs():
    assert prop_section_slugs_for_league("mlb") == ("pitcher-props", "batter-props")


def test_ou_group_id_dispatch():
    assert canonical_market_for_group_id("PitcherStrikeouts(O/U)") == "strikeouts"
    assert canonical_market_for_group_id("Hits(O/U)") == "hits"
    assert canonical_market_for_group_id("TotalBases(O/U)") == "total_bases"
    assert canonical_market_for_group_id("HomeRuns(O/U)") == "home_runs"


def test_uuid_group_id_is_not_ou():
    # Milestone/LIST drawers carry UUID groupIds (deferred, not O/U).
    assert is_ou_group_id("PitcherStrikeouts(O/U)") is True
    assert is_ou_group_id("aec6fadc-51ca-4ca4-a3ef-fc0df5ee6162") is False
    assert canonical_market_for_group_id("aec6fadc-51ca-4ca4-a3ef-fc0df5ee6162") is None
