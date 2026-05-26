import json
from pathlib import Path

import httpx
import pytest

from config.fd_competitions import (
    count_event_page_markets,
    extract_event_page_context,
)
from scrapers.sportsbooks.fd_api import fetch_event_page

EVENT_PAGE_FIXTURES = {
    "player-points": Path("tests/fixtures/fd_event_35639109_player_points.json"),
    "player-rebounds": Path("tests/fixtures/fd_event_35639109_player_rebounds.json"),
    "player-assists": Path("tests/fixtures/fd_event_35639109_player_assists.json"),
}
EVENT_ID = "35639109"


@pytest.fixture
def event_page_payload() -> dict:
    return json.loads(EVENT_PAGE_FIXTURES["player-points"].read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("tab", "tab_title", "main_market_type", "market_count"),
    [
        ("player-points", "Player Points", "PLAYER_A_TOTAL_POINTS", 5),
        ("player-rebounds", "Player Rebounds", "PLAYER_A_TOTAL_REBOUNDS", 4),
        ("player-assists", "Player Assists", "PLAYER_A_TOTAL_ASSISTS", 4),
    ],
)
def test_event_page_fixture_has_event_and_tab_context(
    tab, tab_title, main_market_type, market_count
):
    payload = json.loads(EVENT_PAGE_FIXTURES[tab].read_text(encoding="utf-8"))
    context = extract_event_page_context(payload, tab=tab)

    assert context["event_id"] == EVENT_ID
    assert context["tab"] == tab
    assert context["tab_title"] == tab_title
    assert context["tab_present"] is True
    assert context["tab_id"] == 168

    markets = (payload.get("attachments") or {}).get("markets") or {}
    market_types = {market.get("marketType") for market in markets.values()}
    assert main_market_type in market_types
    assert count_event_page_markets(payload) == market_count


@pytest.mark.asyncio
async def test_fetch_event_page(event_page_payload):
    tab = "player-points"

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=event_page_payload, request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        payload = await fetch_event_page(client, EVENT_ID, tab=tab)

    assert payload is not None
    context = extract_event_page_context(payload, tab=tab)
    assert context["event_id"] == EVENT_ID
    assert context["tab_present"] is True
