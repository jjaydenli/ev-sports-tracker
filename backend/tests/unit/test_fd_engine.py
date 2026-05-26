import json
from pathlib import Path

import httpx
import pytest

from config.fd_markets import (
    FD_DEFAULT_SCRAPE_MARKETS,
    FD_EXTENDED_OU_MARKETS,
)
from parsers.fd_parser import parse_fd_prop, parse_fd_props
from scrapers.sportsbooks.fd_api import count_fd_line_rows, flatten_event_page_response
from scrapers.sportsbooks.fd_engine import (
    FanDuelEngine,
    parse_event_ids,
    scrape_targets_for_markets,
)

EVENT_PAGE_FIXTURES = {
    "points": Path("tests/fixtures/fd_event_35639109_player_points.json"),
    "rebounds": Path("tests/fixtures/fd_event_35639109_player_rebounds.json"),
    "assists": Path("tests/fixtures/fd_event_35639109_player_assists.json"),
}
EVENT_ID = "35639109"
TAB_BY_MARKET = {
    "points": "player-points",
    "rebounds": "player-rebounds",
    "assists": "player-assists",
}


@pytest.fixture
def event_page_payloads() -> dict[str, dict]:
    return {
        market: json.loads(path.read_text(encoding="utf-8"))
        for market, path in EVENT_PAGE_FIXTURES.items()
    }


@pytest.fixture
def event_page_payload(event_page_payloads) -> dict:
    return event_page_payloads["points"]


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


def test_parse_fd_props_expands_grouped_lines():
    grouped = {
        "sportsbook": "FanDuel",
        "player": "Victor Wembanyama",
        "market": "points",
        "event_id": EVENT_ID,
        "lines": [
            {
                "line": 25.5,
                "over_odds": -114,
                "under_odds": -114,
                "is_main_line": True,
            },
            {
                "line": 26.5,
                "over_odds": -110,
                "under_odds": -110,
                "is_main_line": False,
            },
        ],
    }
    rows = parse_fd_props([grouped])
    assert len(rows) == 2
    assert rows[0]["line"] == 25.5
    assert rows[1]["is_main_line"] is False


def test_parse_fd_props_skips_incomplete_rows():
    rows = parse_fd_props(
        [
            {"player": "A", "market": "points", "line": 10.5, "over_odds": -110, "under_odds": -110},
            {"player": "B", "market": "points", "line": None, "over_odds": -110, "under_odds": -110},
        ]
    )
    assert len(rows) == 1


def test_default_markets_include_core_and_extended_stats():
    engine = FanDuelEngine()
    assert set(engine.markets) == set(FD_DEFAULT_SCRAPE_MARKETS)
    assert set(FD_EXTENDED_OU_MARKETS).issubset(set(engine.markets))


def test_scrape_targets_maps_extended_markets_to_sgp_tab():
    targets = scrape_targets_for_markets(["threes", "pra"])
    assert targets == [("same-game-parlay-", {"threes", "pra"})]


@pytest.mark.asyncio
async def test_scrape_flattens_points_from_fixture(event_page_payloads, monkeypatch):
    async def mock_fetch(client, event_id, *, tab, markets=None):
        for market, fixture_tab in TAB_BY_MARKET.items():
            if tab != fixture_tab:
                continue
            if markets is not None and market not in markets:
                continue
            return flatten_event_page_response(
                event_page_payloads[market],
                event_id=event_id,
                tab=tab,
            )
        return []

    monkeypatch.setattr(
        "scrapers.sportsbooks.fd_engine.fetch_and_flatten_event_page",
        mock_fetch,
    )

    engine = FanDuelEngine(event_ids=[EVENT_ID], markets=["points"])
    props = await engine.scrape()

    assert len(props) == 1
    assert props[0]["market"] == "points"
    assert count_fd_line_rows(props) == 18


@pytest.mark.asyncio
async def test_scrape_flattens_all_core_markets(event_page_payloads, monkeypatch):
    async def mock_fetch(client, event_id, *, tab, markets=None):
        for market, fixture_tab in TAB_BY_MARKET.items():
            if tab != fixture_tab:
                continue
            if markets is not None and market not in markets:
                continue
            return flatten_event_page_response(
                event_page_payloads[market],
                event_id=event_id,
                tab=tab,
            )
        return []

    monkeypatch.setattr(
        "scrapers.sportsbooks.fd_engine.fetch_and_flatten_event_page",
        mock_fetch,
    )

    engine = FanDuelEngine(
        event_ids=[EVENT_ID],
        markets=["points", "rebounds", "assists"],
    )
    props = await engine.scrape()

    markets = {prop["market"] for prop in props}
    assert markets == {"points", "rebounds", "assists"}
    assert len(props) == 4
    assert count_fd_line_rows(props) == 18 + 8 + 7


@pytest.mark.asyncio
async def test_scrape_returns_empty_for_unknown_market():
    engine = FanDuelEngine(event_ids=[EVENT_ID], markets=["fantasy_pts"])
    assert await engine.scrape() == []
