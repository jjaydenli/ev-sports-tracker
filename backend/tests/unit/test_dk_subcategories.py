from urllib.parse import parse_qs, urlparse

from config.dk_subcategories import (
    DK_LEAGUE_SLATES,
    DK_MLB_LIVE_STAT_CATEGORIES,
    DK_MLB_STAT_CATEGORIES,
    DK_NBA_MILESTONE_STAT_CATEGORIES,
    DK_NBA_OU_EXTENDED_STAT_CATEGORIES,
    DK_NBA_PENDING_STAT_CATEGORIES,
    DK_NBA_STAT_CATEGORIES,
    DK_WNBA_MILESTONE_STAT_CATEGORIES,
    DK_WNBA_STAT_CATEGORIES,
    build_league_events_query,
    build_league_events_url,
    build_markets_query,
    build_markets_url,
    configured_live_stat_categories_for_league,
    configured_stat_categories_for_league,
    live_stat_categories_for_league,
    milestone_categories_for_league,
    stat_categories_for_league,
)


def test_dk_nba_stat_categories_contains_core_extended():
    assert len(DK_NBA_STAT_CATEGORIES) == 11
    assert DK_NBA_STAT_CATEGORIES["points"] == "12488"
    assert DK_NBA_STAT_CATEGORIES["threes"] == "12497"
    assert DK_NBA_STAT_CATEGORIES["assists"] == "12495"
    assert DK_NBA_STAT_CATEGORIES["pra"] == "5001"


def test_dk_nba_ou_extended_steals_blocks_stl_blk():
    assert DK_NBA_OU_EXTENDED_STAT_CATEGORIES["steals"] == "2713508"
    assert DK_NBA_OU_EXTENDED_STAT_CATEGORIES["blocks"] == "2713780"
    assert DK_NBA_OU_EXTENDED_STAT_CATEGORIES["stl+blk"] == "2713781"
    assert DK_NBA_STAT_CATEGORIES["steals"] == "2713508"


def test_dk_nba_stat_categories_uses_canonical_combo_names():
    assert DK_NBA_STAT_CATEGORIES["pts+reb"] == "9976"
    assert DK_NBA_STAT_CATEGORIES["pts+ast"] == "9973"
    assert DK_NBA_STAT_CATEGORIES["reb+ast"] == "9974"


def test_dk_nba_milestone_stat_categories_verified_ids():
    assert DK_NBA_MILESTONE_STAT_CATEGORIES["points"] == "2716477"
    assert DK_NBA_MILESTONE_STAT_CATEGORIES["rebounds"] == "2716479"
    assert DK_NBA_MILESTONE_STAT_CATEGORIES["assists"] == "2716478"
    assert DK_NBA_MILESTONE_STAT_CATEGORIES["threes"] == "2716480"
    assert DK_NBA_MILESTONE_STAT_CATEGORIES["pts+reb"] == "2716482"
    assert DK_NBA_MILESTONE_STAT_CATEGORIES["pts+ast"] == "2716481"
    assert DK_NBA_MILESTONE_STAT_CATEGORIES["reb+ast"] == "2719560"
    assert DK_NBA_MILESTONE_STAT_CATEGORIES["pra"] == "2716483"
    assert DK_NBA_MILESTONE_STAT_CATEGORIES["blocks"] == "2716484"
    assert DK_NBA_MILESTONE_STAT_CATEGORIES["steals"] == "2716485"
    assert "stl+blk" not in DK_NBA_MILESTONE_STAT_CATEGORIES
    assert len(DK_NBA_MILESTONE_STAT_CATEGORIES) == 10


def test_build_markets_url_steals_milestone_subcategory():
    url = build_markets_url("34183767", DK_NBA_MILESTONE_STAT_CATEGORIES["steals"])
    params = parse_qs(urlparse(url).query)
    assert params["templateVars"] == ["34183767,2716485"]


def test_dk_nba_pending_stat_categories_registered():
    assert DK_NBA_PENDING_STAT_CATEGORIES["turnovers"] is None
    assert DK_NBA_PENDING_STAT_CATEGORIES["fantasy_pts"] is None
    assert "steals" not in DK_NBA_PENDING_STAT_CATEGORIES


def test_build_markets_query_matches_captured_filter():
    query = build_markets_query("34183767", "12488")
    assert query == (
        "$filter=eventId eq '34183767' "
        "AND clientMetadata/subCategoryId eq '12488' "
        "AND tags/all(t: t ne 'SportcastBetBuilder')"
    )


def test_build_markets_url_steals_subcategory():
    url = build_markets_url("34183767", DK_NBA_STAT_CATEGORIES["steals"])
    params = parse_qs(urlparse(url).query)
    assert params["templateVars"] == ["34183767,2713508"]


def test_build_markets_url_matches_captured_points_request():
    url = build_markets_url("34183767", DK_NBA_STAT_CATEGORIES["points"])
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    assert parsed.path.endswith("/event/eventSubcategory/v1/markets")
    assert params["isBatchable"] == ["false"]
    assert params["templateVars"] == ["34183767,12488"]
    assert params["entity"] == ["markets"]
    assert (
        params["marketsQuery"][0]
        == "$filter=eventId eq '34183767' AND clientMetadata/subCategoryId eq '12488' "
        "AND tags/all(t: t ne 'SportcastBetBuilder')"
    )


def test_build_markets_url_supports_batchable_flag():
    url = build_markets_url("34183767", DK_NBA_STAT_CATEGORIES["assists"], batchable=True)
    params = parse_qs(urlparse(url).query)

    assert params["isBatchable"] == ["true"]
    assert params["templateVars"] == ["34183767,12495"]


def test_dk_league_slates_contains_nba():
    assert DK_LEAGUE_SLATES["nba"]["league_id"] == "42648"
    assert DK_LEAGUE_SLATES["nba"]["slate_subcategory_id"] == "4511"


def test_dk_league_slates_contains_mlb():
    assert DK_LEAGUE_SLATES["mlb"]["league_id"] == "84240"
    assert DK_LEAGUE_SLATES["mlb"]["slate_subcategory_id"] == "4519"


def test_dk_league_slates_contains_wnba():
    assert DK_LEAGUE_SLATES["wnba"]["league_id"] == "94682"
    assert DK_LEAGUE_SLATES["wnba"]["slate_subcategory_id"] == "4511"


def test_stat_categories_for_league_wnba_matches_nba():
    assert stat_categories_for_league("wnba") == DK_NBA_STAT_CATEGORIES
    assert stat_categories_for_league("wnba") is DK_WNBA_STAT_CATEGORIES


def test_milestone_categories_for_league_wnba_matches_nba():
    assert milestone_categories_for_league("wnba") == DK_NBA_MILESTONE_STAT_CATEGORIES
    assert milestone_categories_for_league("wnba") is DK_WNBA_MILESTONE_STAT_CATEGORIES


def test_live_stat_categories_for_league_wnba_returns_empty():
    assert live_stat_categories_for_league("wnba") == {}


def test_stat_categories_for_league_mlb():
    assert len(stat_categories_for_league("mlb")) == 13
    assert DK_MLB_STAT_CATEGORIES["hits"] == "6719"
    assert DK_MLB_STAT_CATEGORIES["total_bases"] == "6607"
    assert DK_MLB_STAT_CATEGORIES["singles"] == "17409"
    assert DK_MLB_STAT_CATEGORIES["doubles"] == "17410"
    assert DK_MLB_STAT_CATEGORIES["strikeouts"] == "15221"
    assert DK_MLB_STAT_CATEGORIES["rbi"] == "8025"


def test_configured_stat_categories_for_league_mlb():
    assert len(configured_stat_categories_for_league("mlb")) == 13
    assert configured_stat_categories_for_league("mlb") == DK_MLB_STAT_CATEGORIES


def test_build_league_events_query_matches_captured_filter():
    query = build_league_events_query("42648", "4511")
    assert query == (
        "$filter=leagueId eq '42648' "
        "AND clientMetadata/Subcategories/any(s: s/Id eq '4511')"
    )


def test_build_league_events_url_matches_captured_nba_request():
    url = build_league_events_url("42648", "4511")
    params = parse_qs(urlparse(url).query)

    assert params["isBatchable"] == ["false"]
    assert params["templateVars"] == ["42648,4511"]
    assert params["include"] == ["Events"]
    assert params["entity"] == ["events"]
    assert (
        params["eventsQuery"][0]
        == "$filter=leagueId eq '42648' "
        "AND clientMetadata/Subcategories/any(s: s/Id eq '4511')"
    )


def test_dk_mlb_live_stat_categories_batter_only():
    required = {
        "hits",
        "total_bases",
        "h+r+rbi",
        "runs",
        "singles",
        "doubles",
        "walks",
        "rbi",
    }
    assert required.issubset(DK_MLB_LIVE_STAT_CATEGORIES.keys())
    for pitcher in (
        "strikeouts",
        "earned_runs",
        "total_outs",
        "pitching_walks",
        "hits_allowed",
    ):
        assert pitcher not in DK_MLB_LIVE_STAT_CATEGORIES


def test_live_stat_categories_for_league_mlb_returns_live_map():
    live = live_stat_categories_for_league("mlb")
    assert live is DK_MLB_LIVE_STAT_CATEGORIES


def test_live_stat_categories_for_league_nba_returns_empty():
    assert live_stat_categories_for_league("nba") == {}


def test_configured_live_stat_categories_mlb_partial_fill():
    result = configured_live_stat_categories_for_league("mlb")
    assert result["hits"] == "9502"
    assert result["total_bases"] == "9506"
    assert result["doubles"] == "17472"
    assert "walks" not in result


def test_configured_live_stat_categories_empty_when_all_tbd(monkeypatch):
    # With all-None map, configured_live returns nothing (live scrape is a no-op)
    import config.dk_subcategories as subs

    monkeypatch.setattr(
        subs,
        "DK_MLB_LIVE_STAT_CATEGORIES",
        dict.fromkeys(DK_MLB_LIVE_STAT_CATEGORIES, None),
    )
    assert configured_live_stat_categories_for_league("mlb") == {}


def test_configured_live_stat_categories_returns_filled_ids(monkeypatch):
    filled = {"hits": "9999", "total_bases": None, "runs": "8888"}
    import config.dk_subcategories as subs
    monkeypatch.setattr(subs, "DK_MLB_LIVE_STAT_CATEGORIES", filled)
    result = configured_live_stat_categories_for_league("mlb")
    assert result == {"hits": "9999", "runs": "8888"}
