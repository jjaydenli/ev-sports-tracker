import json
from pathlib import Path

import httpx
import pytest

from config.espn_competitions import (
    extract_event_prop_sections,
    extract_games,
    extract_section_drawers,
    extract_section_ou_drawers,
)
from scrapers.sportsbooks.espn_api import (
    ESPNGraphQLClient,
    _parse_odds,
    count_espn_line_rows,
    flatten_drawer_content,
    flatten_milestone_drawer_content,
    persisted_query_params,
    persisted_query_url,
)

FIX = Path("tests/fixtures")
PITCHER_DRAWER = FIX / "espn_drawer_pitcher_strikeouts.json"
BATTER_DRAWER = FIX / "espn_drawer_batter_hits.json"
LINES_GAMES = FIX / "espn_lines_games.json"
LINES_GAMES_LIVE = FIX / "espn_lines_games_live.json"
DRAWER_MIXED_STATUS = FIX / "espn_drawer_live_mixed_status.json"
EVENT_PAGE = FIX / "espn_event_page.json"
EVENT_SECTION_BATTER = FIX / "espn_event_section_batter.json"
MILESTONE_DRAWER_SINGLES = FIX / "espn_milestone_drawer_singles.json"
EVENT_ID = "0d4827b4-814e-4761-8f15-73d0c62f5e33"
LIVE_EVENT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
FINAL_EVENT_ID = "ffffffff-0000-1111-2222-333333333333"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_parse_odds_even_maps_to_plus_100():
    assert _parse_odds({"odds": {"formattedOdds": "Even"}}) == 100
    assert _parse_odds({"odds": {"formattedOdds": "even"}}) == 100


def test_flatten_ou_with_even_odds():
    payload = {
        "data": {
            "eventDrawer": {
                "id": "Drawer:1:Hits(O/U):Event:" + EVENT_ID,
                "drawerChildren": [
                    {
                        "marketplaceShelfChildren": [
                            {
                                "participant": {"mediumName": "Austin Wells"},
                                "markets": [
                                    {
                                        "name": "Austin Wells Total Hits",
                                        "status": "OPEN",
                                        "type": "TOTAL",
                                        "selections": [
                                            {
                                                "type": "OVER",
                                                "status": "OPEN",
                                                "odds": {"formattedOdds": "Even"},
                                                "points": {"decimalPoints": 0.5},
                                            },
                                            {
                                                "type": "UNDER",
                                                "status": "OPEN",
                                                "odds": {"formattedOdds": "-130"},
                                                "points": {"decimalPoints": 0.5},
                                            },
                                        ],
                                    }
                                ],
                            }
                        ]
                    }
                ],
            }
        }
    }
    props = flatten_drawer_content(payload, event_id=EVENT_ID, league="mlb")
    assert len(props) == 1
    wells = props[0]
    assert wells["player"] == "Austin Wells"
    assert wells["market"] == "hits"
    line = wells["lines"][0]
    assert line["line"] == 0.5
    assert line["over_odds"] == 100
    assert line["under_odds"] == -130


def test_flatten_pitcher_strikeouts_ou():
    props = flatten_drawer_content(_load(PITCHER_DRAWER), event_id=EVENT_ID, league="mlb")
    assert {p["player"] for p in props} == {"Framber Valdez", "Gerrit Cole"}
    assert all(p["market"] == "strikeouts" for p in props)
    valdez = next(p for p in props if p["player"] == "Framber Valdez")
    line = valdez["lines"][0]
    assert line["line"] == 4.5
    assert line["over_odds"] == -155
    assert line["under_odds"] == 110
    assert line["is_main_line"] is True
    assert count_espn_line_rows(props) == 2


def test_flatten_batter_hits_ou():
    props = flatten_drawer_content(_load(BATTER_DRAWER), event_id=EVENT_ID, league="mlb")
    assert props, "expected at least one prop from batter hits drawer"
    assert all(p["market"] == "hits" for p in props)
    chisholm = next(p for p in props if p["player"] == "Jazz Chisholm Jr.")
    assert chisholm["lines"][0]["line"] == 0.5


def test_flatten_derives_group_id_from_drawer_id():
    # group_id omitted -> parsed from data.eventDrawer.id "Drawer:<id>:<groupId>:Event:..".
    props = flatten_drawer_content(_load(PITCHER_DRAWER), event_id=EVENT_ID, league="mlb")
    assert props and props[0]["market"] == "strikeouts"


def test_flatten_non_ou_drawer_returns_empty():
    assert flatten_drawer_content({"data": {"eventDrawer": {}}}, event_id="x", league="mlb") == []


def test_extract_games_from_lines_fixture():
    games = extract_games(_load(LINES_GAMES))
    assert games
    yankees = next(g for g in games if g["event_id"] == EVENT_ID)
    assert yankees["name"] == "New York Yankees @ Detroit Tigers"
    assert yankees["canonical_url"].endswith(EVENT_ID)


def test_extract_event_prop_sections_mlb():
    sections = extract_event_prop_sections(_load(EVENT_PAGE), league="mlb")
    slugs = {s["slug"] for s in sections}
    assert slugs == {"pitcher-props", "batter-props"}


def test_extract_section_drawers_routes_by_kind():
    drawers = extract_section_drawers(_load(EVENT_SECTION_BATTER))
    ou_drawers = [d for d in drawers if d["kind"] == "ou"]
    ms_drawers = [d for d in drawers if d["kind"] == "milestone"]
    ou_group_ids = {d["group_id"] for d in ou_drawers}
    ms_labels = {d["label_text"] for d in ms_drawers}
    assert "Hits(O/U)" in ou_group_ids
    assert all(g.endswith("(O/U)") for g in ou_group_ids)
    assert "Singles" in ms_labels
    assert "Stolen Bases" in ms_labels


def test_extract_section_ou_drawers_compat_filters_milestones():
    # extract_section_ou_drawers (compat alias) still returns only O/U drawers.
    drawers = extract_section_ou_drawers(_load(EVENT_SECTION_BATTER))
    group_ids = {d["group_id"] for d in drawers}
    assert "Hits(O/U)" in group_ids
    assert all(g.endswith("(O/U)") for g in group_ids)


def test_persisted_query_url_and_params():
    url = persisted_query_url("Startup")
    assert "/graphql/persisted_queries/" in url
    params = persisted_query_params("Startup", {"connectToken": "abc"})
    assert params["operationName"] == "Startup"
    assert "connectToken" in params["variables"]
    assert "sha256Hash" in params["extensions"]


@pytest.mark.asyncio
async def test_graphql_client_request_ok():
    payload = _load(PITCHER_DRAWER)

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        api = ESPNGraphQLClient(client, "install", "token")
        result = await api.request("EventDrawerContent", {"id": "x", "sectionSlug": "pitcher-props"})
    assert result["data"]["eventDrawer"]["id"].startswith("Drawer:")


def test_extract_games_live_fixture_statuses():
    games = extract_games(_load(LINES_GAMES_LIVE))
    by_id = {g["event_id"]: g for g in games}
    assert EVENT_ID in by_id
    assert LIVE_EVENT_ID in by_id
    assert FINAL_EVENT_ID in by_id
    assert by_id[EVENT_ID]["status"] == "PRE_GAME"
    assert by_id[LIVE_EVENT_ID]["status"] == "IN_PLAY"
    assert by_id[FINAL_EVENT_ID]["status"] == "FINAL"


def test_flatten_status_guard_drops_closed_market():
    payload = {
        "data": {
            "eventDrawer": {
                "id": "Drawer:1:PitcherStrikeouts(O/U):Event:" + EVENT_ID,
                "drawerChildren": [
                    {
                        "marketplaceShelfChildren": [
                            {
                                "participant": {"mediumName": "Test Player"},
                                "markets": [
                                    {
                                        "name": "Test Player Total Strikeouts",
                                        "status": "CLOSED",
                                        "type": "TOTAL",
                                        "selections": [
                                            {"type": "OVER", "status": "OPEN", "odds": {"formattedOdds": "-110"}, "points": {"decimalPoints": 5.5}},
                                            {"type": "UNDER", "status": "OPEN", "odds": {"formattedOdds": "-110"}, "points": {"decimalPoints": 5.5}},
                                        ],
                                    }
                                ],
                            }
                        ]
                    }
                ],
            }
        }
    }
    props = flatten_drawer_content(payload, event_id=EVENT_ID, league="mlb")
    assert props == []


def test_flatten_status_guard_drops_suspended_market():
    payload = {
        "data": {
            "eventDrawer": {
                "id": "Drawer:1:PitcherStrikeouts(O/U):Event:" + EVENT_ID,
                "drawerChildren": [
                    {
                        "marketplaceShelfChildren": [
                            {
                                "participant": {"mediumName": "Test Player"},
                                "markets": [
                                    {
                                        "name": "Test Player Total Strikeouts",
                                        "status": "SUSPENDED",
                                        "type": "TOTAL",
                                        "selections": [
                                            {"type": "OVER", "status": "OPEN", "odds": {"formattedOdds": "-110"}, "points": {"decimalPoints": 5.5}},
                                            {"type": "UNDER", "status": "OPEN", "odds": {"formattedOdds": "-110"}, "points": {"decimalPoints": 5.5}},
                                        ],
                                    }
                                ],
                            }
                        ]
                    }
                ],
            }
        }
    }
    props = flatten_drawer_content(payload, event_id=EVENT_ID, league="mlb")
    assert props == []


def test_flatten_status_guard_drops_one_sided_open_market():
    payload = {
        "data": {
            "eventDrawer": {
                "id": "Drawer:1:PitcherStrikeouts(O/U):Event:" + EVENT_ID,
                "drawerChildren": [
                    {
                        "marketplaceShelfChildren": [
                            {
                                "participant": {"mediumName": "Test Player"},
                                "markets": [
                                    {
                                        "name": "Test Player Total Strikeouts",
                                        "status": "OPEN",
                                        "type": "TOTAL",
                                        "selections": [
                                            {"type": "OVER", "status": "OPEN", "odds": {"formattedOdds": "-155"}, "points": {"decimalPoints": 4.5}},
                                            {"type": "UNDER", "status": "SUSPENDED", "odds": {"formattedOdds": "+110"}, "points": {"decimalPoints": 4.5}},
                                        ],
                                    }
                                ],
                            }
                        ]
                    }
                ],
            }
        }
    }
    props = flatten_drawer_content(payload, event_id=EVENT_ID, league="mlb")
    assert props == []


def test_flatten_mixed_status_drawer_keeps_only_fully_open():
    props = flatten_drawer_content(_load(DRAWER_MIXED_STATUS), event_id=LIVE_EVENT_ID, league="mlb")
    assert len(props) == 1
    assert props[0]["player"] == "Gerrit Cole"
    assert props[0]["market"] == "strikeouts"
    line = props[0]["lines"][0]
    assert line["over_odds"] == -120
    assert line["under_odds"] == -115


@pytest.mark.asyncio
async def test_graphql_client_remints_on_401(monkeypatch):
    calls = {"n": 0}
    payload = _load(PITCHER_DRAWER)

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(401, json={"error": "unauth"}, request=request)
        return httpx.Response(200, json=payload, request=request)

    async def fake_ensure(*, client, force_refresh):
        return "install", "fresh-token"

    monkeypatch.setattr("scrapers.sportsbooks.espn_api.ensure_espn_token", fake_ensure)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        api = ESPNGraphQLClient(client, "install", "stale-token")
        result = await api.request("EventDrawerContent", {"id": "x", "sectionSlug": "pitcher-props"})

    assert calls["n"] == 2
    assert api.token == "fresh-token"
    assert result is not None


def test_flatten_milestone_singles_from_fixture():
    rows = flatten_milestone_drawer_content(
        _load(MILESTONE_DRAWER_SINGLES),
        event_id=EVENT_ID,
        league="mlb",
        label_text="Singles",
        section_slug="batter-props",
    )
    players = {r["player"] for r in rows}
    assert "Jazz Chisholm Jr." in players
    assert "A. Judge" in players
    assert all(r["market"] == "singles" for r in rows)
    assert all(r["line_kind"] == "milestone" for r in rows)
    assert all(r["sportsbook"] == "ESPN" for r in rows)
    assert all(r["under_odds"] is None for r in rows)

    chisholm_rows = [r for r in rows if r["player"] == "Jazz Chisholm Jr."]
    lines = {r["line"] for r in chisholm_rows}
    assert 0.5 in lines
    assert 1.5 in lines

    row_05 = next(r for r in chisholm_rows if r["line"] == 0.5)
    assert row_05["over_odds"] == -175
    assert row_05["is_main_line"] is True
    assert row_05["milestone_threshold"] == 1

    row_15 = next(r for r in chisholm_rows if r["line"] == 1.5)
    assert row_15["over_odds"] == 250
    assert row_15["is_main_line"] is False

    judge_rows = [r for r in rows if r["player"] == "A. Judge"]
    assert len(judge_rows) == 1
    assert judge_rows[0]["line"] == 0.5
    assert judge_rows[0]["over_odds"] == -155


def test_flatten_milestone_drops_suspended_selection():
    # J. Chisholm row has only a SUSPENDED selection — must not appear.
    rows = flatten_milestone_drawer_content(
        _load(MILESTONE_DRAWER_SINGLES),
        event_id=EVENT_ID,
        league="mlb",
        label_text="Singles",
    )
    assert not any(r["player"] == "J. Chisholm" for r in rows)


def test_flatten_milestone_drops_suspended_market():
    # "Someone Else" is in a SUSPENDED market — must not appear.
    rows = flatten_milestone_drawer_content(
        _load(MILESTONE_DRAWER_SINGLES),
        event_id=EVENT_ID,
        league="mlb",
        label_text="Singles",
    )
    assert not any(r["player"] == "Someone Else" for r in rows)


def test_flatten_milestone_unknown_label_returns_empty():
    rows = flatten_milestone_drawer_content(
        _load(MILESTONE_DRAWER_SINGLES),
        event_id=EVENT_ID,
        league="mlb",
        label_text="UnknownStat",
    )
    assert rows == []
