import json
from pathlib import Path

import httpx
import pytest

from scrapers.sportsbooks.dk_api import flatten_markets_response
from scrapers.sportsbooks.dk_engine import (
    DraftKingsEngine,
    extract_event_id_from_url,
    parse_event_ids,
)

FIXTURE_PATH = Path("tests/fixtures/dk_markets_points_34183767.json")
EVENT_ID = "34183767"


@pytest.fixture
def points_payload() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_extract_event_id_from_url():
    url = (
        "https://sportsbook.draftkings.com/event/tor-raptors-%40-cle-cavaliers/"
        "34058465?category=all-odds&subcategory=points"
    )
    assert extract_event_id_from_url(url) == "34058465"


def test_parse_event_ids_deduplicates_and_prefers_explicit_ids():
    urls = [
        "https://sportsbook.draftkings.com/event/game-a/34058465",
        "https://sportsbook.draftkings.com/event/game-b/34058465",
    ]
    assert parse_event_ids(event_ids=["34183767"], game_urls=urls) == [
        "34183767",
        "34058465",
    ]


@pytest.mark.asyncio
async def test_scrape_fetches_configured_markets(points_payload, monkeypatch):
    async def mock_fetch(
        client: httpx.AsyncClient, event_id: str, market: str
    ) -> list[dict]:
        if market != "points":
            return []
        return flatten_markets_response(
            points_payload, event_id=event_id, market=market
        )

    monkeypatch.setattr(
        "scrapers.sportsbooks.dk_engine.fetch_and_flatten_markets",
        mock_fetch,
    )

    engine = DraftKingsEngine(event_ids=[EVENT_ID], markets=["points"])
    props = await engine.scrape()

    assert len(props) == 16
    assert props[0]["market"] == "points"


@pytest.mark.asyncio
async def test_scrape_returns_empty_when_slate_has_no_events(monkeypatch):
    async def mock_slate(client, league="nba", statuses=None):
        return []

    monkeypatch.setattr(
        "scrapers.sportsbooks.dk_engine.fetch_league_event_ids",
        mock_slate,
    )

    engine = DraftKingsEngine()
    assert await engine.scrape() == []


@pytest.mark.asyncio
async def test_scrape_discovers_event_ids_from_league_slate(
    points_payload, monkeypatch
):
    async def mock_slate(client, league="nba", statuses=None):
        return ["34183767"]

    async def mock_fetch(
        client: httpx.AsyncClient, event_id: str, market: str
    ) -> list[dict]:
        if market != "points":
            return []
        return flatten_markets_response(
            points_payload, event_id=event_id, market=market
        )

    monkeypatch.setattr(
        "scrapers.sportsbooks.dk_engine.fetch_league_event_ids",
        mock_slate,
    )
    monkeypatch.setattr(
        "scrapers.sportsbooks.dk_engine.fetch_and_flatten_markets",
        mock_fetch,
    )

    engine = DraftKingsEngine(markets=["points"])
    props = await engine.scrape()

    assert len(props) == 16


@pytest.mark.asyncio
async def test_scrape_rejects_unknown_markets():
    engine = DraftKingsEngine(event_ids=[EVENT_ID], markets=["unknown-stat"])
    assert await engine.scrape() == []
