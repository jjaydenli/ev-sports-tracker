import json
from pathlib import Path

import httpx
import pytest

from config.espn_competitions import (
    extract_event_prop_sections,
    extract_games,
    extract_section_ou_drawers,
)
from scrapers.sportsbooks.espn_api import (
    ESPNGraphQLClient,
    count_espn_line_rows,
    flatten_drawer_content,
    persisted_query_params,
    persisted_query_url,
)

FIX = Path("tests/fixtures")
PITCHER_DRAWER = FIX / "espn_drawer_pitcher_strikeouts.json"
BATTER_DRAWER = FIX / "espn_drawer_batter_hits.json"
LINES_GAMES = FIX / "espn_lines_games.json"
EVENT_PAGE = FIX / "espn_event_page.json"
EVENT_SECTION_BATTER = FIX / "espn_event_section_batter.json"
EVENT_ID = "0d4827b4-814e-4761-8f15-73d0c62f5e33"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


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


def test_extract_section_ou_drawers_filters_milestones():
    drawers = extract_section_ou_drawers(_load(EVENT_SECTION_BATTER))
    group_ids = {d["group_id"] for d in drawers}
    assert "Hits(O/U)" in group_ids
    # No UUID (milestone/LIST) groupIds survive the O/U filter.
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
