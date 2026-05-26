import json
from pathlib import Path

import httpx
import pytest

from parsers.fd_parser import parse_fd_prop, parse_fd_props
from scrapers.sportsbooks.fd_api import flatten_event_page_response
from scrapers.sportsbooks.fd_engine import FanDuelEngine, parse_event_ids

EVENT_PAGE_FIXTURE_PATH = Path("tests/fixtures/fd_event_35639109_player_points.json")
EVENT_ID = "35639109"
TAB = "player-points"


@pytest.fixture
def event_page_payload() -> dict:
    return json.loads(EVENT_PAGE_FIXTURE_PATH.read_text(encoding="utf-8"))


def test_parse_event_ids_from_game_url():
    url = (
        "https://sportsbook.fanduel.com/basketball/nba/"
        "san-antonio-spurs-@-oklahoma-city-thunder-35639109"
    )
    assert parse_event_ids(event_ids=["35652199"], game_urls=[url]) == [
        "35652199",
        "35639109",
    ]


def test_parse_fd_prop_normalizes_market():
    raw = {
        "sportsbook": "FanDuel",
        "player": "Victor Wembanyama",
        "market": "points",
        "line": 25.5,
        "over_odds": -114,
        "under_odds": -114,
        "is_main_line": True,
    }
    parsed = parse_fd_prop(raw)
    assert parsed is not None
    assert parsed["market"] == "points"
    assert parsed["line_kind"] == "ou"


def test_parse_fd_props_skips_incomplete_rows():
    rows = parse_fd_props(
        [
            {"player": "A", "market": "points", "line": 10.5, "over_odds": -110, "under_odds": -110},
            {"player": "B", "market": "points", "line": None, "over_odds": -110, "under_odds": -110},
        ]
    )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_scrape_flattens_points_from_fixture(event_page_payload, monkeypatch):
    async def mock_fetch(client, event_id, *, tab):
        if tab != TAB:
            return []
        return flatten_event_page_response(
            event_page_payload,
            event_id=event_id,
            tab=tab,
        )

    monkeypatch.setattr(
        "scrapers.sportsbooks.fd_engine.fetch_and_flatten_event_page",
        mock_fetch,
    )

    engine = FanDuelEngine(event_ids=[EVENT_ID], markets=["points"])
    props = await engine.scrape()

    assert len(props) == 18
    assert props[0]["market"] == "points"


@pytest.mark.asyncio
async def test_scrape_returns_empty_for_unknown_market():
    engine = FanDuelEngine(event_ids=[EVENT_ID], markets=["fantasy_pts"])
    assert await engine.scrape() == []
