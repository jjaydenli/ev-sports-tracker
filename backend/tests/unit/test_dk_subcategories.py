from urllib.parse import parse_qs, urlparse

from config.dk_subcategories import (
    DK_LEAGUE_SLATES,
    DK_MLB_LIVE_MILESTONE_STAT_CATEGORIES,
    DK_MLB_LIVE_STAT_CATEGORIES,
    DK_MLB_PREGAME_MILESTONE_STAT_CATEGORIES,
    DK_MLB_PREGAME_STAT_CATEGORIES,
    DK_NBA_PENDING_STAT_CATEGORIES,
    DK_NBA_PREGAME_MILESTONE_STAT_CATEGORIES,
    DK_NBA_PREGAME_STAT_CATEGORIES,
    DK_SUBCATEGORIES,
    DK_WNBA_PREGAME_MILESTONE_STAT_CATEGORIES,
    DK_WNBA_PREGAME_STAT_CATEGORIES,
    PropTabs,
    build_league_events_query,
    build_league_events_url,
    build_markets_query,
    build_markets_url,
    subcategories_for_league,
)


def _configured_registry_tabs() -> list[tuple[str, str, str, str]]:
    """Walk DK_SUBCATEGORIES independently of subcategory_market_labels (test oracle)."""
    tabs: list[tuple[str, str, str, str]] = []
    for subs in DK_SUBCATEGORIES.values():
        for state_name, state_tabs in (("pregame", subs.pregame), ("live", subs.live)):
            for kind, market_map in (("ou", state_tabs.ou), ("milestone", state_tabs.milestone)):
                configured = (
                    state_tabs.configured_ou
                    if kind == "ou"
                    else state_tabs.configured_milestone
                )
                for market, sid in configured.items():
                    tabs.append((state_name, kind, market, sid))
    return tabs


def test_dk_nba_stat_categories_merged_ou_ids():
    assert len(DK_NBA_PREGAME_STAT_CATEGORIES) == 11
    assert DK_NBA_PREGAME_STAT_CATEGORIES["points"] == "12488"
    assert DK_NBA_PREGAME_STAT_CATEGORIES["threes"] == "12497"
    assert DK_NBA_PREGAME_STAT_CATEGORIES["assists"] == "12495"
    assert DK_NBA_PREGAME_STAT_CATEGORIES["pra"] == "5001"
    assert DK_NBA_PREGAME_STAT_CATEGORIES["steals"] == "2713508"
    assert DK_NBA_PREGAME_STAT_CATEGORIES["blocks"] == "2713780"
    assert DK_NBA_PREGAME_STAT_CATEGORIES["stl+blk"] == "2713781"


def test_dk_nba_stat_categories_uses_canonical_combo_names():
    assert DK_NBA_PREGAME_STAT_CATEGORIES["pts+reb"] == "9976"
    assert DK_NBA_PREGAME_STAT_CATEGORIES["pts+ast"] == "9973"
    assert DK_NBA_PREGAME_STAT_CATEGORIES["reb+ast"] == "9974"


def test_dk_nba_milestone_stat_categories_verified_ids():
    assert DK_NBA_PREGAME_MILESTONE_STAT_CATEGORIES["points"] == "2716477"
    assert DK_NBA_PREGAME_MILESTONE_STAT_CATEGORIES["rebounds"] == "2716479"
    assert DK_NBA_PREGAME_MILESTONE_STAT_CATEGORIES["assists"] == "2716478"
    assert DK_NBA_PREGAME_MILESTONE_STAT_CATEGORIES["threes"] == "2716480"
    assert DK_NBA_PREGAME_MILESTONE_STAT_CATEGORIES["pts+reb"] == "2716482"
    assert DK_NBA_PREGAME_MILESTONE_STAT_CATEGORIES["pts+ast"] == "2716481"
    assert DK_NBA_PREGAME_MILESTONE_STAT_CATEGORIES["reb+ast"] == "2719560"
    assert DK_NBA_PREGAME_MILESTONE_STAT_CATEGORIES["pra"] == "2716483"
    assert DK_NBA_PREGAME_MILESTONE_STAT_CATEGORIES["blocks"] == "2716484"
    assert DK_NBA_PREGAME_MILESTONE_STAT_CATEGORIES["steals"] == "2716485"
    assert "stl+blk" not in DK_NBA_PREGAME_MILESTONE_STAT_CATEGORIES
    assert len(DK_NBA_PREGAME_MILESTONE_STAT_CATEGORIES) == 10


def test_build_markets_url_steals_milestone_subcategory():
    url = build_markets_url("34183767", DK_NBA_PREGAME_MILESTONE_STAT_CATEGORIES["steals"])
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
    url = build_markets_url("34183767", DK_NBA_PREGAME_STAT_CATEGORIES["steals"])
    params = parse_qs(urlparse(url).query)
    assert params["templateVars"] == ["34183767,2713508"]


def test_build_markets_url_matches_captured_points_request():
    url = build_markets_url("34183767", DK_NBA_PREGAME_STAT_CATEGORIES["points"])
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
    url = build_markets_url("34183767", DK_NBA_PREGAME_STAT_CATEGORIES["assists"], batchable=True)
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


def test_subcategories_for_league_wnba_aliases_nba():
    wnba = subcategories_for_league("wnba")
    assert wnba.pregame.ou is DK_WNBA_PREGAME_STAT_CATEGORIES
    assert wnba.pregame.ou == DK_NBA_PREGAME_STAT_CATEGORIES
    assert wnba.pregame.milestone is DK_WNBA_PREGAME_MILESTONE_STAT_CATEGORIES
    assert wnba.pregame.milestone == DK_NBA_PREGAME_MILESTONE_STAT_CATEGORIES


def test_subcategories_for_league_unknown_falls_back_to_nba():
    assert subcategories_for_league("xfl") is subcategories_for_league("nba")


def test_subcategories_for_league_is_case_insensitive():
    assert subcategories_for_league("MLB").pregame.ou is DK_MLB_PREGAME_STAT_CATEGORIES


def test_subcategories_for_league_mlb_pregame_ou():
    mlb = subcategories_for_league("mlb")
    assert mlb.pregame.ou is DK_MLB_PREGAME_STAT_CATEGORIES
    assert len(mlb.pregame.ou) == 15
    assert DK_MLB_PREGAME_STAT_CATEGORIES["hits"] == "6719"
    assert DK_MLB_PREGAME_STAT_CATEGORIES["total_bases"] == "6607"
    assert DK_MLB_PREGAME_STAT_CATEGORIES["singles"] == "17409"
    assert DK_MLB_PREGAME_STAT_CATEGORIES["doubles"] == "17410"
    assert DK_MLB_PREGAME_STAT_CATEGORIES["pitching_strikeouts"] == "15221"
    assert DK_MLB_PREGAME_STAT_CATEGORIES["rbi"] == "8025"


def test_mlb_pregame_configured_ou_matches_full_map():
    # No pregame O/U id is pending, so configured == the raw map.
    assert subcategories_for_league("mlb").pregame.configured_ou == DK_MLB_PREGAME_STAT_CATEGORIES


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


def test_dk_mlb_live_stat_categories_batter_and_pitcher_ids_verified():
    batter_configured = {
        "hits",
        "total_bases",
        "h+r+rbi",
        "runs",
        "singles",
        "doubles",
        "batting_walks",
        "rbi",
    }
    for market in batter_configured:
        assert DK_MLB_LIVE_STAT_CATEGORIES[market] is not None
    # Pitcher live O/U, verified against a live game 2026-07-25.
    assert DK_MLB_LIVE_STAT_CATEGORIES["pitching_strikeouts"] == "12960"
    assert DK_MLB_LIVE_STAT_CATEGORIES["earned_runs"] == "19874"
    assert DK_MLB_LIVE_STAT_CATEGORIES["hits_allowed"] == "12962"
    assert DK_MLB_LIVE_STAT_CATEGORIES["pitching_walks"] == "12963"
    assert DK_MLB_LIVE_STAT_CATEGORIES["total_outs"] == "17476"
    assert DK_MLB_LIVE_STAT_CATEGORIES["h+bb+er"] == "19913"


def test_subcategories_for_league_mlb_live_ou_is_live_map():
    assert subcategories_for_league("mlb").live.ou is DK_MLB_LIVE_STAT_CATEGORIES


def test_nba_and_wnba_live_ids_not_probed_yet():
    # Live NBA/WNBA props exist on DK; the maps are empty only until a live
    # DevTools capture fills them (same pending state as MLB milestone).
    for league in ("nba", "wnba"):
        live = subcategories_for_league(league).live
        assert live.ou == {}
        assert live.milestone == {}


def test_mlb_pregame_milestone_ids_verified():
    milestone = subcategories_for_league("mlb").pregame.milestone
    assert milestone is DK_MLB_PREGAME_MILESTONE_STAT_CATEGORIES
    assert DK_MLB_PREGAME_MILESTONE_STAT_CATEGORIES["home_runs"] == "17319"
    assert DK_MLB_PREGAME_MILESTONE_STAT_CATEGORIES["hits"] == "17320"
    assert DK_MLB_PREGAME_MILESTONE_STAT_CATEGORIES["total_bases"] == "17321"
    assert DK_MLB_PREGAME_MILESTONE_STAT_CATEGORIES["rbi"] == "17322"
    assert DK_MLB_PREGAME_MILESTONE_STAT_CATEGORIES["stolen_bases"] == "18726"
    assert DK_MLB_PREGAME_MILESTONE_STAT_CATEGORIES["xbh"] == "19451"
    assert DK_MLB_PREGAME_MILESTONE_STAT_CATEGORIES["h+r+rbi"] == "17843"
    assert DK_MLB_PREGAME_MILESTONE_STAT_CATEGORIES["pitching_strikeouts"] == "17323"
    assert DK_MLB_PREGAME_MILESTONE_STAT_CATEGORIES["batting_strikeouts"] == "17849"
    assert len(subcategories_for_league("mlb").pregame.configured_milestone) == 18


def test_mlb_live_milestone_batter_ids_verified():
    mlb = subcategories_for_league("mlb")
    assert mlb.live.milestone is DK_MLB_LIVE_MILESTONE_STAT_CATEGORIES
    assert DK_MLB_LIVE_MILESTONE_STAT_CATEGORIES["batting_strikeouts"] == "17490"
    assert DK_MLB_LIVE_MILESTONE_STAT_CATEGORIES["home_runs"] == "17482"
    assert DK_MLB_LIVE_MILESTONE_STAT_CATEGORIES["total_bases"] == "17480"
    assert DK_MLB_LIVE_MILESTONE_STAT_CATEGORIES["rbi"] == "17479"
    assert DK_MLB_LIVE_MILESTONE_STAT_CATEGORIES["h+r+rbi"] == "18773"
    assert DK_MLB_LIVE_MILESTONE_STAT_CATEGORIES["stolen_bases"] == "18775"
    assert DK_MLB_LIVE_MILESTONE_STAT_CATEGORIES["batting_walks"] == "18774"
    assert DK_MLB_LIVE_MILESTONE_STAT_CATEGORIES["runs"] == "17488"
    assert DK_MLB_LIVE_MILESTONE_STAT_CATEGORIES["singles"] == "17485"
    assert DK_MLB_LIVE_MILESTONE_STAT_CATEGORIES["doubles"] == "17486"
    assert DK_MLB_LIVE_MILESTONE_STAT_CATEGORIES["triples"] == "17487"
    assert DK_MLB_LIVE_MILESTONE_STAT_CATEGORIES["hits"] == "17483"


def test_mlb_live_configured_ou_all_batter_and_pitcher_ids_set():
    result = subcategories_for_league("mlb").live.configured_ou
    assert result["hits"] == "9502"
    assert result["total_bases"] == "9506"
    assert result["doubles"] == "17472"
    assert result["batting_walks"] == "9536"
    assert result["pitching_strikeouts"] == "12960"
    assert result["h+bb+er"] == "19913"
    # 8 batter + 6 pitcher markets, all configured.
    assert len(result) == 14


def test_prop_tabs_configured_drops_none_and_tbd():
    tabs = PropTabs(
        ou={"a": "1", "b": None, "c": "TBD", "d": "2"},
        milestone={"x": None, "y": "9"},
    )
    assert tabs.configured_ou == {"a": "1", "d": "2"}
    assert tabs.configured_milestone == {"y": "9"}


def test_prop_tabs_configured_empty_when_all_placeholders():
    tabs = PropTabs(ou=dict.fromkeys(DK_MLB_LIVE_STAT_CATEGORIES, None), milestone={})
    assert tabs.configured_ou == {}
    assert tabs.configured_milestone == {}


def test_every_configured_subcategory_id_is_labelable():
    from scrapers.sportsbooks.dk_api import _prop_subcategory_market_label

    for _state, _kind, _market, sid in _configured_registry_tabs():
        assert _prop_subcategory_market_label(sid) is not None


def test_subcategory_labels_match_registry_position():
    from config.dk_subcategories import subcategory_market_labels

    labels = subcategory_market_labels()
    for state, kind, market, sid in _configured_registry_tabs():
        assert labels[sid] == f"{state}:{kind}:{market}"


def test_no_subcategory_id_maps_to_conflicting_meanings():
    meanings_by_id: dict[str, set[tuple[str, str, str]]] = {}
    for state, kind, market, sid in _configured_registry_tabs():
        meanings_by_id.setdefault(sid, set()).add((state, kind, market))
    for sid, meanings in meanings_by_id.items():
        assert len(meanings) == 1, f"{sid} maps to {meanings}"
