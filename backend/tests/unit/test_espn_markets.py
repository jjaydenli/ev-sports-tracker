from config.espn_competitions import ESPN_LEAGUE_SLATES
from config.espn_markets import (
    ESPN_MLB_DEFAULT_SCRAPE_MARKETS,
    canonical_market_for_group_id,
    canonical_market_for_milestone_label,
    default_scrape_markets_for_league,
    is_milestone_label,
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


def test_pitcher_ou_group_id_dispatch():
    # Pitcher O/U drawers captured live (Outs Recorded / Hits Allowed / Walks Allowed).
    assert canonical_market_for_group_id("OutsRecorded(O/U)") == "total_outs"
    assert canonical_market_for_group_id("HitsAllowed(O/U)") == "hits_allowed"
    assert canonical_market_for_group_id("WalksAllowed(O/U)") == "pitching_walks"
    for gid in ("OutsRecorded(O/U)", "HitsAllowed(O/U)", "WalksAllowed(O/U)"):
        assert is_ou_group_id(gid) is True


def test_uuid_group_id_is_not_ou():
    # Milestone/LIST drawers carry UUID groupIds; they are now dispatched via labelText.
    assert is_ou_group_id("PitcherStrikeouts(O/U)") is True
    assert is_ou_group_id("aec6fadc-51ca-4ca4-a3ef-fc0df5ee6162") is False
    assert canonical_market_for_group_id("aec6fadc-51ca-4ca4-a3ef-fc0df5ee6162") is None


def test_milestone_label_dispatch():
    assert is_milestone_label("Singles") is True
    assert is_milestone_label("Doubles") is True
    assert is_milestone_label("Runs") is True
    assert is_milestone_label("Stolen Bases") is True
    assert is_milestone_label("Hits") is False
    assert is_milestone_label("Hits(O/U)") is False
    assert is_milestone_label(None) is False


def test_canonical_market_for_milestone_label():
    assert canonical_market_for_milestone_label("Singles") == "singles"
    assert canonical_market_for_milestone_label("Doubles") == "doubles"
    assert canonical_market_for_milestone_label("Runs") == "runs"
    assert canonical_market_for_milestone_label("Stolen Bases") == "stolen_bases"
    assert canonical_market_for_milestone_label("Hits") is None
    assert canonical_market_for_milestone_label(None) is None


def test_milestone_markets_in_default_scrape():
    markets = known_markets_for_league("mlb")
    assert "singles" in markets
    assert "doubles" in markets
    assert "runs" in markets
    assert "stolen_bases" in markets
