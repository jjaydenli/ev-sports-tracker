from urllib.parse import parse_qs, urlparse

from config.dk_subcategories import (
    DK_LEAGUE_SLATES,
    DK_STAT_CATEGORIES,
    build_league_events_query,
    build_league_events_url,
    build_markets_query,
    build_markets_url,
)


def test_dk_stat_categories_contains_seven_markets():
    assert len(DK_STAT_CATEGORIES) == 7
    assert DK_STAT_CATEGORIES["points"] == "12488"
    assert DK_STAT_CATEGORIES["assists"] == "12495"
    assert DK_STAT_CATEGORIES["pra"] == "5001"


def test_dk_stat_categories_uses_canonical_combo_names():
    assert DK_STAT_CATEGORIES["pts+reb"] == "9976"
    assert DK_STAT_CATEGORIES["pts+ast"] == "9973"
    assert DK_STAT_CATEGORIES["reb+ast"] == "9974"


def test_build_markets_query_matches_captured_filter():
    query = build_markets_query("34183767", "12488")
    assert query == (
        "$filter=eventId eq '34183767' "
        "AND clientMetadata/subCategoryId eq '12488' "
        "AND tags/all(t: t ne 'SportcastBetBuilder')"
    )


def test_build_markets_url_matches_captured_points_request():
    url = build_markets_url("34183767", DK_STAT_CATEGORIES["points"])
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
    url = build_markets_url("34183767", DK_STAT_CATEGORIES["assists"], batchable=True)
    params = parse_qs(urlparse(url).query)

    assert params["isBatchable"] == ["true"]
    assert params["templateVars"] == ["34183767,12495"]


def test_dk_league_slates_contains_nba():
    assert DK_LEAGUE_SLATES["nba"]["league_id"] == "42648"
    assert DK_LEAGUE_SLATES["nba"]["subcategory_id"] == "4511"


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
