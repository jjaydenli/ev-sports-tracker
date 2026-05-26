import json
from pathlib import Path

import httpx
import pytest

from config.fd_competitions import (
    build_content_managed_page_url,
    build_event_page_url,
    extract_event_ids,
    parse_event_id_from_url,
)
from scrapers.sportsbooks.fd_api import fetch_league_event_ids

LEAGUE_FIXTURE_PATH = Path("tests/fixtures/fd_league_nba_events.json")
NBA_COMPETITION_ID = "10547864"


@pytest.fixture
def league_payload() -> dict:
    return json.loads(LEAGUE_FIXTURE_PATH.read_text(encoding="utf-8"))


def test_build_content_managed_page_url_includes_nba_page():
    url = build_content_managed_page_url("nba")

    assert "content-managed-page" in url
    assert "customPageId=nba" in url
    assert "_ak=" in url


def test_build_event_page_url_includes_event_and_tab():
    url = build_event_page_url("35639109", tab="player-points")

    assert "event-page" in url
    assert "eventId=35639109" in url
    assert "tab=player-points" in url


def test_parse_event_id_from_url():
    url = (
        "https://sportsbook.fanduel.com/basketball/nba/"
        "san-antonio-spurs-@-oklahoma-city-thunder-35639109"
    )

    assert parse_event_id_from_url(url) == "35639109"


def test_extract_event_ids_returns_matchups_only(league_payload):
    event_ids = extract_event_ids(
        league_payload, competition_id=NBA_COMPETITION_ID, require_matchup=True
    )

    assert event_ids == ["35639109", "35652199", "35652200"]


def test_extract_event_ids_can_include_specials(league_payload):
    """Draft/awards share NBA competition_id; futures use 12739957."""
    event_ids = extract_event_ids(
        league_payload, competition_id=NBA_COMPETITION_ID, require_matchup=False
    )

    assert "28279720" in event_ids
    assert "28301194" in event_ids
    assert "34409523" not in event_ids


@pytest.mark.asyncio
async def test_fetch_league_event_ids(league_payload):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=league_payload, request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        event_ids = await fetch_league_event_ids(client, league="nba")

    assert event_ids == ["35639109", "35652199", "35652200"]
