import json
from pathlib import Path

import httpx
import pytest

from config.fd_competitions import (
    count_event_page_markets,
    extract_event_page_context,
)
from scrapers.sportsbooks.fd_api import fetch_event_page

EVENT_PAGE_FIXTURE_PATH = Path("tests/fixtures/fd_event_35639109_player_points.json")
EVENT_ID = "35639109"
TAB = "player-points"


@pytest.fixture
def event_page_payload() -> dict:
    return json.loads(EVENT_PAGE_FIXTURE_PATH.read_text(encoding="utf-8"))


def test_event_page_fixture_has_event_and_tab_context(event_page_payload):
    context = extract_event_page_context(event_page_payload, tab=TAB)

    assert context["event_id"] == EVENT_ID
    assert context["tab"] == TAB
    assert context["tab_title"] == "Player Points"
    assert context["tab_present"] is True
    assert context["tab_id"] == 168


def test_event_page_fixture_has_sample_markets(event_page_payload):
    markets = (event_page_payload.get("attachments") or {}).get("markets") or {}
    market_types = {market.get("marketType") for market in markets.values()}

    assert "PLAYER_A_TOTAL_POINTS" in market_types
    assert "PLAYER_A_ALT_TOTAL_POINTS" in market_types
    assert count_event_page_markets(event_page_payload) == 5


@pytest.mark.asyncio
async def test_fetch_event_page(event_page_payload):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=event_page_payload, request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        payload = await fetch_event_page(client, EVENT_ID, tab=TAB)

    assert payload is not None
    context = extract_event_page_context(payload, tab=TAB)
    assert context["event_id"] == EVENT_ID
    assert context["tab_present"] is True
