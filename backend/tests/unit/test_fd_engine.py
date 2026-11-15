import json
from pathlib import Path

import httpx
import pytest

from config.fd_markets import (
    FD_EXTENDED_OU_MARKETS,
    default_scrape_markets_for_league,
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
MLB_PITCHER_FIXTURE = Path("tests/fixtures/fd_event_35730475_pitcher_props.json")
EVENT_ID = "35639109"
MLB_EVENT_ID = "35730475"
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
    assert set(engine.markets) == set(default_scrape_markets_for_league("nba"))
    assert set(FD_EXTENDED_OU_MARKETS).issubset(set(engine.markets))


def test_mlb_default_markets_include_strikeouts():
    engine = FanDuelEngine(league="mlb")
    assert "pitching_strikeouts" in engine.markets


def test_scrape_targets_maps_extended_markets_to_sgp_tab():
    targets = scrape_targets_for_markets(["threes", "pra"], league="nba")
    assert targets == [("same-game-parlay-", {"threes", "pra"})]


@pytest.fixture
def mlb_pitcher_payload() -> dict:
    return json.loads(MLB_PITCHER_FIXTURE.read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_scrape_mlb_strikeouts_from_fixture(mlb_pitcher_payload, monkeypatch):
    async def mock_fetch(client, event_id, *, tab, markets=None, league="nba", is_live=False):
        if league != "mlb" or tab != "pitcher-props":
            return []
        return flatten_event_page_response(
            mlb_pitcher_payload,
            event_id=event_id,
            tab=tab,
            markets=markets,
            league=league,
        )

    monkeypatch.setattr(
        "scrapers.sportsbooks.fd_engine.fetch_and_flatten_event_page",
        mock_fetch,
    )

    engine = FanDuelEngine(
        event_ids=[MLB_EVENT_ID], markets=["pitching_strikeouts"], league="mlb"
    )
    props = await engine.scrape()

    assert len(props) == 2
    assert {prop["market"] for prop in props} == {"pitching_strikeouts"}
    assert props[0]["league"] == "MLB"
    assert count_fd_line_rows(props) == 2


@pytest.mark.asyncio
async def test_scrape_flattens_points_from_fixture(event_page_payloads, monkeypatch):
    async def mock_fetch(client, event_id, *, tab, markets=None, league="nba", is_live=False):
        for market, fixture_tab in TAB_BY_MARKET.items():
            if tab != fixture_tab:
                continue
            if markets is not None and market not in markets:
                continue
            return flatten_event_page_response(
                event_page_payloads[market],
                event_id=event_id,
                tab=tab,
                league=league,
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
    async def mock_fetch(client, event_id, *, tab, markets=None, league="nba", is_live=False):
        for market, fixture_tab in TAB_BY_MARKET.items():
            if tab != fixture_tab:
                continue
            if markets is not None and market not in markets:
                continue
            return flatten_event_page_response(
                event_page_payloads[market],
                event_id=event_id,
                tab=tab,
                league=league,
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


LIVE_SLATE_FIXTURE = Path("tests/fixtures/fd_league_nba_live.json")
LIVE_EVENT_ID = "36257605"
LIVE_PAGE_FIXTURES = {
    "live-sgp": Path("tests/fixtures/fd_event_36257605_live_sgp.json"),
    "player-combos": Path("tests/fixtures/fd_event_36257605_player_combos.json"),
}
# The 2026-11-01 slate's NBA matchups other than the two in progress.
PREGAME_EVENT_IDS = {
    "36262171", "36262172", "36262173", "36262174", "36262175", "36262176",
    "36262177", "36262178", "36262180", "36262181", "36262182", "36262184",
}


def _route_fd_traffic(monkeypatch) -> None:
    """Serve the live slate, LAC@GS's live tabs, and a captured pregame points page.

    Live pages answer only for LAC@GS (TOR@LAL has no capture, so it 404s), and the
    pregame page answers only on its own tab, so each row's tab and event show which
    fetch produced it.
    """
    slate = json.loads(LIVE_SLATE_FIXTURE.read_text(encoding="utf-8"))
    live_pages = {
        tab: json.loads(path.read_text(encoding="utf-8"))
        for tab, path in LIVE_PAGE_FIXTURES.items()
    }
    pregame_points = json.loads(EVENT_PAGE_FIXTURES["points"].read_text(encoding="utf-8"))

    def handler(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if params.get("page") == "CUSTOM":
            return httpx.Response(200, json=slate, request=request)
        tab, event_id = params.get("tab"), params.get("eventId")
        if event_id == LIVE_EVENT_ID and tab in live_pages:
            return httpx.Response(200, json=live_pages[tab], request=request)
        if event_id in PREGAME_EVENT_IDS and tab == TAB_BY_MARKET["points"]:
            return httpx.Response(200, json=pregame_points, request=request)
        return httpx.Response(404, request=request)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        "scrapers.sportsbooks.fd_engine.httpx.AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )


@pytest.mark.asyncio
async def test_scrape_routes_live_and_pregame_events_to_their_tabs(monkeypatch):
    """Oracle: the slate's per-market inPlay flags and the capture's rows per tab.

    Kris Dunn's assists 4.5 is on LAC@GS's live-sgp page, and pts+reb+ast is only on
    its player-combos page, so both live tabs must have been fetched for that event.
    """
    _route_fd_traffic(monkeypatch)

    props = await FanDuelEngine(league="nba").scrape()

    live = [row for row in props if row.get("is_live")]
    pregame = [row for row in props if not row.get("is_live")]
    assert {row["event_id"] for row in live} == {LIVE_EVENT_ID}
    assert {row["tab"] for row in live} == set(LIVE_PAGE_FIXTURES)
    assert ("Kris Dunn", "assists") in {(row["player"], row["market"]) for row in live}
    assert "pra" in {row["market"] for row in live}
    assert {row["event_id"] for row in pregame} == PREGAME_EVENT_IDS
    assert {row["tab"] for row in pregame} == {TAB_BY_MARKET["points"]}


@pytest.mark.asyncio
async def test_scrape_live_only_fetches_only_live_events(monkeypatch):
    _route_fd_traffic(monkeypatch)

    props = await FanDuelEngine(league="nba", live_only=True).scrape()

    assert props
    assert {row["event_id"] for row in props} == {LIVE_EVENT_ID}
    assert all(row.get("is_live") for row in props)


@pytest.mark.asyncio
async def test_scrape_live_only_with_explicit_event_ids_returns_nothing(monkeypatch):
    """Explicit ids skip the slate, so their state is unknown and they stay pregame-only.

    A pregame id is the case that matters: its points page is served, so fetching it
    under live_only would return rows.
    """
    _route_fd_traffic(monkeypatch)

    engine = FanDuelEngine(event_ids=["36262178"], league="nba", live_only=True)

    assert await engine.scrape() == []


@pytest.mark.asyncio
async def test_scrape_returns_empty_for_unknown_market():
    engine = FanDuelEngine(event_ids=[EVENT_ID], markets=["fantasy_pts"])
    assert await engine.scrape() == []
