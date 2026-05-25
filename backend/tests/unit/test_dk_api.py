import json
from pathlib import Path

import httpx
import pytest

from config.dk_subcategories import DK_STAT_CATEGORIES
from scrapers.sportsbooks.dk_api import (
    extract_event_ids,
    fetch_and_flatten_markets,
    fetch_event_subcategory_markets,
    fetch_league_event_ids,
    flatten_markets_response,
    parse_american_odds,
)

FIXTURE_PATH = Path("tests/fixtures/dk_markets_points_34183767.json")
LEAGUE_FIXTURE_PATH = Path("tests/fixtures/dk_league_nba_events.json")
EVENT_ID = "34183767"


@pytest.fixture
def points_payload() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def league_payload() -> dict:
    return json.loads(LEAGUE_FIXTURE_PATH.read_text(encoding="utf-8"))


def test_parse_american_odds_handles_unicode_minus():
    assert parse_american_odds({"american": "\u2212111"}) == -111
    assert parse_american_odds({"american": "+107"}) == 107


def test_flatten_markets_response_produces_one_row_per_player(points_payload):
    props = flatten_markets_response(
        points_payload,
        event_id=EVENT_ID,
        market="points",
    )

    assert len(props) == 16
    shai = next(prop for prop in props if prop["player"] == "Shai Gilgeous-Alexander")
    assert shai["market"] == "points"
    assert shai["line"] == 29.5
    assert shai["over_odds"] == -111
    assert shai["under_odds"] == -115
    assert shai["market_id"] == "336952528"
    assert shai["subcategory_id"] == DK_STAT_CATEGORIES["points"]


def test_flatten_markets_response_uses_market_key_directly(points_payload):
    props = flatten_markets_response(
        points_payload,
        event_id=EVENT_ID,
        market="pts+reb",
    )

    assert props
    assert props[0]["market"] == "pts+reb"
    assert props[0]["subcategory_id"] == DK_STAT_CATEGORIES["pts+reb"]


@pytest.mark.asyncio
async def test_fetch_event_subcategory_markets_returns_none_on_http_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, request=request, text="forbidden")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await fetch_event_subcategory_markets(
            client, EVENT_ID, DK_STAT_CATEGORIES["points"]
        )

    assert result is None


def test_extract_event_ids_returns_not_started_only(league_payload):
    event_ids = extract_event_ids(league_payload)

    assert event_ids == ["34183767"]


def test_extract_event_ids_can_include_all_statuses(league_payload):
    event_ids = extract_event_ids(league_payload, statuses=set())

    assert "34178452" in event_ids
    assert "34183767" in event_ids


@pytest.mark.asyncio
async def test_fetch_league_event_ids(league_payload):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=league_payload, request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        event_ids = await fetch_league_event_ids(client, league="nba")

    assert event_ids == ["34183767"]


@pytest.mark.asyncio
async def test_fetch_and_flatten_markets(points_payload):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=points_payload, request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        props = await fetch_and_flatten_markets(client, EVENT_ID, "points")

    assert len(props) == 16
    assert props[0]["sportsbook"] == "DraftKings"
