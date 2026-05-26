import json
from pathlib import Path

import httpx
import pytest

from config.fd_markets import parse_player_ou_market_type
from scrapers.sportsbooks.fd_api import (
    flatten_event_page_response,
    flatten_player_ou_market,
    merge_prop_rows,
    parse_fd_american_odds,
)
from scrapers.sportsbooks.fd_api import fetch_and_flatten_event_page

EVENT_PAGE_FIXTURE_PATH = Path("tests/fixtures/fd_event_35639109_player_points.json")
EVENT_ID = "35639109"
TAB = "player-points"
WEMBANYAMA = "Victor Wembanyama"


@pytest.fixture
def event_page_payload() -> dict:
    return json.loads(EVENT_PAGE_FIXTURE_PATH.read_text(encoding="utf-8"))


def test_parse_player_ou_market_type():
    assert parse_player_ou_market_type("PLAYER_A_TOTAL_POINTS") == ("points", False)
    assert parse_player_ou_market_type("PLAYER_H_ALT_TOTAL_REBOUNDS") == (
        "rebounds",
        True,
    )
    assert parse_player_ou_market_type("TO_SCORE_25+_POINTS") is None
    assert parse_player_ou_market_type("MONEY_LINE") is None


def test_parse_fd_american_odds_from_fixture(event_page_payload):
    markets = event_page_payload["attachments"]["markets"]
    main = next(
        m for m in markets.values() if m["marketType"] == "PLAYER_A_TOTAL_POINTS"
    )
    over_runner = main["runners"][0]
    assert parse_fd_american_odds(over_runner) == -114


def test_flatten_main_line_wembanyama(event_page_payload):
    markets = event_page_payload["attachments"]["markets"]
    main = next(
        m for m in markets.values() if m["marketType"] == "PLAYER_A_TOTAL_POINTS"
    )

    props = flatten_player_ou_market(
        main,
        event_id=EVENT_ID,
        tab=TAB,
        canonical_market="points",
    )

    assert len(props) == 1
    row = props[0]
    assert row["player"] == WEMBANYAMA
    assert row["line"] == 25.5
    assert row["over_odds"] == -114
    assert row["under_odds"] == -114
    assert row["is_main_line"] is True


def test_flatten_alt_ladder_uses_one_point_increments(event_page_payload):
    markets = event_page_payload["attachments"]["markets"]
    alt = next(
        m for m in markets.values() if m["marketType"] == "PLAYER_A_ALT_TOTAL_POINTS"
    )

    props = flatten_player_ou_market(
        alt,
        event_id=EVENT_ID,
        tab=TAB,
        canonical_market="points",
    )

    wemby = sorted(
        [p for p in props if p["player"] == WEMBANYAMA],
        key=lambda row: row["line"],
    )
    assert len(wemby) == 18
    assert wemby[0]["line"] == 17.5
    assert wemby[-1]["line"] == 34.5
    assert all(row["is_main_line"] is False for row in wemby)
    diffs = {wemby[i + 1]["line"] - wemby[i]["line"] for i in range(len(wemby) - 1)}
    assert diffs == {1.0}


def test_flatten_event_page_skips_milestones_and_game_lines(event_page_payload):
    props = flatten_event_page_response(
        event_page_payload,
        event_id=EVENT_ID,
        tab=TAB,
    )

    assert props
    market_types = {prop["market_type"] for prop in props}
    assert "TO_SCORE_25+_POINTS" not in market_types
    assert "MONEY_LINE" not in market_types
    assert "TOTAL_POINTS_(OVER/UNDER)" not in market_types
    assert all(prop["market"] == "points" for prop in props)


def test_merge_prop_rows_prefers_main_line(event_page_payload):
    props = flatten_event_page_response(
        event_page_payload,
        event_id=EVENT_ID,
        tab=TAB,
    )
    wemby_255 = next(
        p for p in props if p["player"] == WEMBANYAMA and p["line"] == 25.5
    )
    assert wemby_255["is_main_line"] is True


@pytest.mark.asyncio
async def test_fetch_and_flatten_event_page(event_page_payload):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=event_page_payload, request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        props = await fetch_and_flatten_event_page(client, EVENT_ID, tab=TAB)

    assert len(props) == 18
    assert merge_prop_rows(props) == props
