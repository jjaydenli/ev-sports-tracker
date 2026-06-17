import json
from pathlib import Path

import httpx
import pytest

from config.dk_subcategories import (
    DK_MLB_LIVE_STAT_CATEGORIES,
    DK_MLB_STAT_CATEGORIES,
    DK_NBA_STAT_CATEGORIES,
)
from scrapers.sportsbooks.dk_api import flatten_markets_response
from scrapers.sportsbooks.dk_engine import (
    DraftKingsEngine,
    extract_event_id_from_url,
    parse_event_ids,
)

FIXTURE_PATH = Path("tests/fixtures/dk_markets_points_34183767.json")
MLB_HITS_FIXTURE_PATH = Path("tests/fixtures/dk_markets_mlb_hits.json")
MLB_LEAGUE_WITH_LIVE_FIXTURE_PATH = Path(
    "tests/fixtures/dk_league_mlb_events_with_live.json"
)
EVENT_ID = "34183767"
MLB_EVENT_ID = "34267452"
MLB_LIVE_EVENT_ID = "34267999"


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


@pytest.fixture
def mock_dk_warm_up(monkeypatch):
    async def _noop_warm_up(client, league="nba"):
        return None

    monkeypatch.setattr(
        "scrapers.sportsbooks.dk_engine.warm_up_dk_session",
        _noop_warm_up,
    )


@pytest.mark.asyncio
async def test_scrape_fetches_configured_markets(
    points_payload, monkeypatch, mock_dk_warm_up
):
    async def mock_fetch(
        client: httpx.AsyncClient, event_id: str, market: str
    ) -> list[dict]:
        if market != "points":
            return []
        return flatten_markets_response(
            points_payload,
            event_id=event_id,
            market=market,
            prop_subcategory_id=DK_NBA_STAT_CATEGORIES[market],
        )

    async def mock_event_markets(
        client: httpx.AsyncClient,
        event_id: str,
        markets: list[str] | None = None,
        **kwargs,
    ) -> list[dict]:
        if event_id != EVENT_ID:
            return []
        return await mock_fetch(client, event_id, "points")

    monkeypatch.setattr(
        "scrapers.sportsbooks.dk_engine.fetch_event_all_markets",
        mock_event_markets,
    )

    engine = DraftKingsEngine(event_ids=[EVENT_ID], markets=["points"])
    props = await engine.scrape()

    assert len(props) == 16
    assert props[0]["market"] == "points"
    assert props[0]["league"] == "NBA"


@pytest.mark.asyncio
async def test_scrape_returns_empty_when_slate_has_no_events(monkeypatch):
    async def mock_league(client, league="nba"):
        return None

    monkeypatch.setattr(
        "scrapers.sportsbooks.dk_engine.fetch_league_events",
        mock_league,
    )

    engine = DraftKingsEngine()
    assert await engine.scrape() == []


@pytest.mark.asyncio
async def test_scrape_discovers_event_ids_from_league_slate(
    points_payload, monkeypatch, mock_dk_warm_up
):
    async def mock_league(client, league="nba"):
        return {"events": [{"id": "34183767", "status": "NOT_STARTED"}]}

    async def mock_event_markets(
        client: httpx.AsyncClient,
        event_id: str,
        markets: list[str] | None = None,
        **kwargs,
    ) -> list[dict]:
        market = (markets or ["points"])[0]
        if market != "points":
            return []
        return flatten_markets_response(
            points_payload,
            event_id=event_id,
            market=market,
            prop_subcategory_id=DK_NBA_STAT_CATEGORIES[market],
        )

    monkeypatch.setattr(
        "scrapers.sportsbooks.dk_engine.fetch_league_events",
        mock_league,
    )
    monkeypatch.setattr(
        "scrapers.sportsbooks.dk_engine.fetch_event_all_markets",
        mock_event_markets,
    )

    engine = DraftKingsEngine(markets=["points"])
    props = await engine.scrape()

    assert len(props) == 16
    assert props[0]["league"] == "NBA"


@pytest.mark.asyncio
async def test_scrape_rejects_unknown_markets():
    engine = DraftKingsEngine(event_ids=[EVENT_ID], markets=["unknown-stat"])
    assert await engine.scrape() == []


@pytest.mark.asyncio
async def test_scrape_mlb_hits(monkeypatch, mock_dk_warm_up):
    hits_payload = json.loads(MLB_HITS_FIXTURE_PATH.read_text(encoding="utf-8"))

    async def mock_event_markets(
        client: httpx.AsyncClient,
        event_id: str,
        markets: list[str] | None = None,
        **kwargs,
    ) -> list[dict]:
        market = (markets or ["hits"])[0]
        if event_id != MLB_EVENT_ID or market != "hits":
            return []
        return flatten_markets_response(
            hits_payload,
            event_id=event_id,
            market=market,
            prop_subcategory_id=DK_MLB_STAT_CATEGORIES[market],
        )

    monkeypatch.setattr(
        "scrapers.sportsbooks.dk_engine.fetch_event_all_markets",
        mock_event_markets,
    )

    engine = DraftKingsEngine(
        event_ids=[MLB_EVENT_ID], markets=["hits"], league="mlb"
    )
    props = await engine.scrape()

    assert len(props) == 18
    assert props[0]["market"] == "hits"
    assert props[0]["league"] == "MLB"


@pytest.mark.asyncio
async def test_scrape_mlb_discovers_pregame_and_live_from_slate(
    monkeypatch, mock_dk_warm_up
):
    slate = json.loads(MLB_LEAGUE_WITH_LIVE_FIXTURE_PATH.read_text(encoding="utf-8"))
    hits_payload = json.loads(MLB_HITS_FIXTURE_PATH.read_text(encoding="utf-8"))
    fetched_event_ids: list[str] = []

    async def mock_league(client, league="nba"):
        if league.lower() == "mlb":
            return slate
        return None

    async def mock_event_markets(
        client: httpx.AsyncClient,
        event_id: str,
        markets: list[str] | None = None,
        **kwargs,
    ) -> list[dict]:
        fetched_event_ids.append(event_id)
        market = (markets or ["hits"])[0]
        if event_id != MLB_EVENT_ID or market != "hits":
            return []
        return flatten_markets_response(
            hits_payload,
            event_id=event_id,
            market=market,
            prop_subcategory_id=DK_MLB_STAT_CATEGORIES[market],
        )

    monkeypatch.setattr(
        "scrapers.sportsbooks.dk_engine.fetch_league_events",
        mock_league,
    )
    monkeypatch.setattr(
        "scrapers.sportsbooks.dk_engine.fetch_event_all_markets",
        mock_event_markets,
    )
    import config.dk_subcategories as subs

    monkeypatch.setattr(
        subs,
        "DK_MLB_LIVE_STAT_CATEGORIES",
        dict.fromkeys(DK_MLB_LIVE_STAT_CATEGORIES, None),
    )

    engine = DraftKingsEngine(markets=["hits"], league="mlb")
    props = await engine.scrape()

    assert MLB_EVENT_ID in fetched_event_ids
    assert MLB_LIVE_EVENT_ID not in fetched_event_ids
    assert len(props) == 18
    assert all(not p.get("is_live") for p in props)


@pytest.mark.asyncio
async def test_scrape_mlb_live_tags_is_live_when_categories_configured(
    monkeypatch, mock_dk_warm_up
):
    slate = json.loads(MLB_LEAGUE_WITH_LIVE_FIXTURE_PATH.read_text(encoding="utf-8"))
    hits_payload = json.loads(MLB_HITS_FIXTURE_PATH.read_text(encoding="utf-8"))
    fetched: list[tuple[str, list[str] | None]] = []

    async def mock_league(client, league="nba"):
        if league.lower() == "mlb":
            return slate
        return None

    async def mock_event_markets(
        client: httpx.AsyncClient,
        event_id: str,
        markets: list[str] | None = None,
        **kwargs,
    ) -> list[dict]:
        fetched.append((event_id, markets))
        market = (markets or ["hits"])[0]
        if market != "hits":
            return []
        if event_id == MLB_LIVE_EVENT_ID:
            return flatten_markets_response(
                hits_payload,
                event_id=event_id,
                market=market,
                prop_subcategory_id=DK_MLB_STAT_CATEGORIES[market],
            )
        if event_id == MLB_EVENT_ID:
            return flatten_markets_response(
                hits_payload,
                event_id=event_id,
                market=market,
                prop_subcategory_id=DK_MLB_STAT_CATEGORIES[market],
            )
        return []

    import config.dk_subcategories as subs

    monkeypatch.setattr(
        subs,
        "DK_MLB_LIVE_STAT_CATEGORIES",
        {**DK_MLB_LIVE_STAT_CATEGORIES, "hits": DK_MLB_STAT_CATEGORIES["hits"]},
    )
    monkeypatch.setattr(
        "scrapers.sportsbooks.dk_engine.fetch_league_events",
        mock_league,
    )
    monkeypatch.setattr(
        "scrapers.sportsbooks.dk_engine.fetch_event_all_markets",
        mock_event_markets,
    )

    engine = DraftKingsEngine(markets=["hits"], league="mlb")
    props = await engine.scrape()

    fetched_ids = {event_id for event_id, _ in fetched}
    assert fetched_ids == {MLB_EVENT_ID, MLB_LIVE_EVENT_ID}
    live_props = [p for p in props if p.get("is_live")]
    pregame_props = [p for p in props if not p.get("is_live")]
    assert len(live_props) == 18
    assert len(pregame_props) == 18
    assert live_props[0]["market"] == "hits"
