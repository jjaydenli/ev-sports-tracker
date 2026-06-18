import asyncio
import json
from pathlib import Path

import httpx
import pytest

from config.dk_subcategories import (
    DK_MLB_STAT_CATEGORIES,
    DK_NBA_MILESTONE_STAT_CATEGORIES,
    DK_NBA_STAT_CATEGORIES,
    build_markets_url,
)
from scrapers.sportsbooks.dk_api import (
    LIVE_EVENT_STATUSES,
    SCRAPABLE_EVENT_STATUSES,
    extract_event_ids,
    fetch_and_flatten_all_for_market,
    fetch_and_flatten_markets,
    fetch_event_subcategory_markets,
    fetch_league_event_ids,
    flatten_markets_response,
    flatten_milestone_markets_response,
    infer_canonical_market_from_dk_label,
    infer_canonical_market_from_dk_payload,
    milestone_threshold_to_line,
    parse_american_odds,
)

FIXTURE_PATH = Path("tests/fixtures/dk_markets_points_34183767.json")
STEALS_OU_FIXTURE_PATH = Path("tests/fixtures/dk_markets_steals_ou_34183767.json")
STEALS_MILESTONE_FIXTURE_PATH = Path(
    "tests/fixtures/dk_markets_steals_milestone_34183767.json"
)
LEAGUE_FIXTURE_PATH = Path("tests/fixtures/dk_league_nba_events.json")
MLB_HITS_FIXTURE_PATH = Path("tests/fixtures/dk_markets_mlb_hits.json")
MLB_TOTAL_BASES_FIXTURE_PATH = Path("tests/fixtures/dk_markets_mlb_total_bases.json")
MLB_LEAGUE_FIXTURE_PATH = Path("tests/fixtures/dk_league_mlb_events.json")
MLB_LEAGUE_WITH_LIVE_FIXTURE_PATH = Path(
    "tests/fixtures/dk_league_mlb_events_with_live.json"
)
EVENT_ID = "34183767"
MLB_EVENT_ID = "34267452"


@pytest.fixture
def points_payload() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def league_payload() -> dict:
    return json.loads(LEAGUE_FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def steals_ou_payload() -> dict:
    return json.loads(STEALS_OU_FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def steals_milestone_payload() -> dict:
    return json.loads(STEALS_MILESTONE_FIXTURE_PATH.read_text(encoding="utf-8"))


def test_parse_american_odds_handles_unicode_minus():
    assert parse_american_odds({"american": "\u2212111"}) == -111
    assert parse_american_odds({"american": "+107"}) == 107


def test_flatten_markets_response_produces_one_row_per_player(points_payload):
    props = flatten_markets_response(
        points_payload,
        event_id=EVENT_ID,
        market="points",
        prop_subcategory_id=DK_NBA_STAT_CATEGORIES["points"],
    )

    assert len(props) == 16
    shai = next(prop for prop in props if prop["player"] == "Shai Gilgeous-Alexander")
    assert shai["market"] == "points"
    assert shai["line"] == 29.5
    assert shai["over_odds"] == -111
    assert shai["under_odds"] == -115
    assert shai["is_main_line"] is True
    assert shai["market_id"] == "336952528"
    assert shai["subcategory_id"] == DK_NBA_STAT_CATEGORIES["points"]
    assert shai["line_kind"] == "ou"


def test_flatten_steals_ou_fixture(steals_ou_payload):
    props = flatten_markets_response(
        steals_ou_payload,
        event_id=EVENT_ID,
        market="steals",
        prop_subcategory_id=DK_NBA_STAT_CATEGORIES["steals"],
    )
    assert len(props) == 2
    main = next(p for p in props if p["line"] == 1.5)
    assert main["player"] == "Alex Caruso"
    assert main["over_odds"] == -120
    assert main["under_odds"] == -110
    assert main["subcategory_id"] == "2713508"


def test_infer_canonical_market_from_dk_label():
    assert infer_canonical_market_from_dk_label("Shai Gilgeous-Alexander Points O/U") == "points"
    assert infer_canonical_market_from_dk_label("Alex Caruso Steals") == "steals"
    assert infer_canonical_market_from_dk_label("Pts + Reb + Ast O/U") == "pra"
    assert infer_canonical_market_from_dk_label("Pts + Ast O/U") == "pts+ast"
    assert infer_canonical_market_from_dk_label("Steals + Blocks O/U") == "stl+blk"
    assert infer_canonical_market_from_dk_label("Luis Arraez Hits O/U") == "hits"
    assert infer_canonical_market_from_dk_label("Casey Schmitt Total Bases O/U") == "total_bases"
    assert infer_canonical_market_from_dk_label("Connor Prielipp Hits Allowed O/U") == "hits_allowed"
    assert infer_canonical_market_from_dk_label("Connor Prielipp Strikeouts Thrown O/U") == "strikeouts"
    assert infer_canonical_market_from_dk_label("Byron Buxton RBIs O/U") == "rbi"


def test_infer_canonical_market_from_steals_milestone_fixture(steals_milestone_payload):
    assert infer_canonical_market_from_dk_payload(steals_milestone_payload) == "steals"


def test_milestone_threshold_to_line():
    assert milestone_threshold_to_line(2) == 1.5
    assert milestone_threshold_to_line(1) == 0.5


def test_flatten_milestone_steals_fixture(steals_milestone_payload):
    props = flatten_milestone_markets_response(
        steals_milestone_payload,
        event_id=EVENT_ID,
        market="steals",
        prop_subcategory_id=DK_NBA_MILESTONE_STAT_CATEGORIES["steals"],
    )
    assert len(props) == 3
    two_plus = next(p for p in props if p["milestone_threshold"] == 2)
    assert two_plus["line"] == 1.5
    assert two_plus["line_kind"] == "milestone"
    assert two_plus["over_odds"] == 110
    assert two_plus["under_odds"] is None


def test_flatten_markets_response_uses_market_key_directly(points_payload):
    props = flatten_markets_response(
        points_payload,
        event_id=EVENT_ID,
        market="pts+reb",
        prop_subcategory_id=DK_NBA_STAT_CATEGORIES["pts+reb"],
    )

    assert props
    assert props[0]["market"] == "pts+reb"
    assert props[0]["subcategory_id"] == DK_NBA_STAT_CATEGORIES["pts+reb"]


@pytest.mark.asyncio
async def test_fetch_event_subcategory_markets_returns_none_on_http_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, request=request, text="forbidden")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await fetch_event_subcategory_markets(
            client, EVENT_ID, DK_NBA_STAT_CATEGORIES["points"]
        )

    assert result is None


@pytest.mark.asyncio
async def test_fetch_event_subcategory_markets_retries_transient_403(points_payload):
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(403, request=request, text="blocked")
        return httpx.Response(200, json=points_payload, request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await fetch_event_subcategory_markets(
            client, EVENT_ID, DK_NBA_STAT_CATEGORIES["points"]
        )

    assert result == points_payload
    assert attempts == 2


def test_flatten_mlb_hits_fixture():
    payload = json.loads(MLB_HITS_FIXTURE_PATH.read_text(encoding="utf-8"))
    props = flatten_markets_response(
        payload,
        event_id=MLB_EVENT_ID,
        market="hits",
        prop_subcategory_id=DK_MLB_STAT_CATEGORIES["hits"],
    )
    assert len(props) == 18
    arraez = next(p for p in props if p["player"] == "Luis Arraez")
    assert arraez["market"] == "hits"
    assert arraez["subcategory_id"] == "6719"
    assert arraez["line_kind"] == "ou"


def test_flatten_mlb_total_bases_fixture():
    payload = json.loads(MLB_TOTAL_BASES_FIXTURE_PATH.read_text(encoding="utf-8"))
    props = flatten_markets_response(
        payload,
        event_id=MLB_EVENT_ID,
        market="total_bases",
        prop_subcategory_id=DK_MLB_STAT_CATEGORIES["total_bases"],
    )
    assert props
    assert props[0]["market"] == "total_bases"
    assert props[0]["subcategory_id"] == "6607"


def test_infer_canonical_market_from_mlb_hits_fixture():
    payload = json.loads(MLB_HITS_FIXTURE_PATH.read_text(encoding="utf-8"))
    assert infer_canonical_market_from_dk_payload(payload) == "hits"


@pytest.mark.parametrize(
    ("fixture_name", "market", "subcategory_id"),
    [
        ("dk_markets_mlb_singles.json", "singles", "17409"),
        ("dk_markets_mlb_strikeouts.json", "strikeouts", "15221"),
        ("dk_markets_mlb_hits_allowed.json", "hits_allowed", "9886"),
        ("dk_markets_mlb_rbi.json", "rbi", "8025"),
    ],
)
def test_flatten_mlb_ou_fixtures(fixture_name, market, subcategory_id):
    path = Path("tests/fixtures") / fixture_name
    payload = json.loads(path.read_text(encoding="utf-8"))
    event_id = payload["markets"][0]["eventId"]
    props = flatten_markets_response(
        payload,
        event_id=event_id,
        market=market,
        prop_subcategory_id=subcategory_id,
    )
    assert props
    assert props[0]["market"] == market
    assert props[0]["subcategory_id"] == subcategory_id
    assert props[0]["line_kind"] == "ou"


def test_infer_canonical_market_from_mlb_hits_allowed_fixture():
    payload = json.loads(
        Path("tests/fixtures/dk_markets_mlb_hits_allowed.json").read_text(encoding="utf-8")
    )
    assert infer_canonical_market_from_dk_payload(payload) == "hits_allowed"


def test_extract_event_ids_mlb_league_fixture():
    payload = json.loads(MLB_LEAGUE_FIXTURE_PATH.read_text(encoding="utf-8"))
    event_ids = extract_event_ids(payload)
    assert MLB_EVENT_ID in event_ids
    assert len(event_ids) >= 10


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


@pytest.mark.asyncio
async def test_fetch_and_flatten_all_for_market_merges_ou_and_milestone(
    steals_ou_payload, steals_milestone_payload
):
    ou_url = build_markets_url(EVENT_ID, DK_NBA_STAT_CATEGORIES["steals"])
    ms_url = build_markets_url(EVENT_ID, DK_NBA_MILESTONE_STAT_CATEGORIES["steals"])

    async def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == ou_url:
            return httpx.Response(200, json=steals_ou_payload, request=request)
        if str(request.url) == ms_url:
            return httpx.Response(200, json=steals_milestone_payload, request=request)
        return httpx.Response(404, request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        props = await fetch_and_flatten_all_for_market(client, EVENT_ID, "steals")

    assert len(props) == 5
    kinds = {p["line_kind"] for p in props}
    assert kinds == {"ou", "milestone"}


def test_live_event_statuses_constant():
    assert "IN_PROGRESS" in LIVE_EVENT_STATUSES
    assert "STARTED" in LIVE_EVENT_STATUSES
    assert "NOT_STARTED" not in LIVE_EVENT_STATUSES


def test_extract_event_ids_pregame_only_by_default():
    payload = {
        "events": [
            {"id": "100", "status": "NOT_STARTED"},
            {"id": "200", "status": "IN_PROGRESS"},
            {"id": "300", "status": "COMPLETED"},
        ]
    }
    result = extract_event_ids(payload)
    assert result == ["100"]


def test_extract_event_ids_live_only():
    payload = {
        "events": [
            {"id": "100", "status": "NOT_STARTED"},
            {"id": "200", "status": "IN_PROGRESS"},
        ]
    }
    result = extract_event_ids(payload, statuses=LIVE_EVENT_STATUSES)
    assert result == ["200"]


def test_extract_event_ids_pregame_and_live():
    payload = {
        "events": [
            {"id": "100", "status": "NOT_STARTED"},
            {"id": "200", "status": "IN_PROGRESS"},
            {"id": "300", "status": "COMPLETED"},
        ]
    }
    combined = SCRAPABLE_EVENT_STATUSES | LIVE_EVENT_STATUSES
    result = extract_event_ids(payload, statuses=combined)
    assert set(result) == {"100", "200"}
    assert "300" not in result


def test_extract_event_ids_mlb_live_fixture():
    payload = json.loads(MLB_LEAGUE_WITH_LIVE_FIXTURE_PATH.read_text(encoding="utf-8"))
    pregame = extract_event_ids(payload)
    live = extract_event_ids(payload, statuses=LIVE_EVENT_STATUSES)
    combined = extract_event_ids(
        payload, statuses=SCRAPABLE_EVENT_STATUSES | LIVE_EVENT_STATUSES
    )
    assert pregame == ["34267452"]
    assert live == ["34267999"]
    assert set(combined) == {"34267452", "34267999"}


def test_extract_event_ids_started_status():
    payload = {
        "events": [
            {"id": "100", "status": "NOT_STARTED"},
            {"id": "400", "status": "STARTED"},
        ]
    }
    result = extract_event_ids(payload, statuses=LIVE_EVENT_STATUSES)
    assert result == ["400"]


def test_fetch_event_subcategory_markets_survives_separate_asyncio_runs(points_payload):
    """pipeline_runner calls asyncio.run once per league; sem must rebind."""

    async def fetch_once() -> dict | None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=points_payload, request=request)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await fetch_event_subcategory_markets(
                client, EVENT_ID, DK_NBA_STAT_CATEGORIES["points"]
            )

    first = asyncio.run(fetch_once())
    second = asyncio.run(fetch_once())
    assert first == points_payload
    assert second == points_payload
