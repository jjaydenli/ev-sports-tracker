import json
from pathlib import Path

import httpx
import pytest

from config.fd_markets import parse_player_ou_market_type
from scrapers.sportsbooks.fd_api import (
    count_fd_line_rows,
    flatten_event_page_response,
    flatten_player_ou_market,
    group_fd_line_rows,
    merge_prop_rows,
    parse_fd_american_odds,
)
from scrapers.sportsbooks.fd_api import fetch_and_flatten_event_page

EVENT_PAGE_FIXTURE_PATH = Path("tests/fixtures/fd_event_35639109_player_points.json")
EVENT_ID = "35639109"
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
    assert parse_player_ou_market_type("PLAYER_A_TOTAL_MADE_3_POINT_FIELD_GOALS") == (
        "threes",
        False,
    )
    assert parse_player_ou_market_type("PLAYER_B_ALT_TOTAL_PTS_+_REB_+_AST") == (
        "pra",
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
        tab="player-points",
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
        tab="player-points",
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


def test_group_fd_line_rows_combines_main_and_alt():
    line_rows = [
        {
            "sportsbook": "FanDuel",
            "event_id": EVENT_ID,
            "tab": "player-points",
            "player": WEMBANYAMA,
            "market": "points",
            "line": 25.5,
            "line_kind": "ou",
            "over_odds": -114,
            "under_odds": -114,
            "is_main_line": True,
            "market_type": "PLAYER_A_TOTAL_POINTS",
        },
        {
            "sportsbook": "FanDuel",
            "event_id": EVENT_ID,
            "tab": "player-points",
            "player": WEMBANYAMA,
            "market": "points",
            "line": 26.5,
            "line_kind": "ou",
            "over_odds": -110,
            "under_odds": -110,
            "is_main_line": False,
            "market_type": "PLAYER_A_ALT_TOTAL_POINTS",
        },
    ]

    grouped = group_fd_line_rows(line_rows)

    assert len(grouped) == 1
    assert grouped[0]["player"] == WEMBANYAMA
    assert len(grouped[0]["lines"]) == 2
    assert count_fd_line_rows(grouped) == 2


def test_flatten_event_page_skips_milestones_and_game_lines(event_page_payload):
    props = flatten_event_page_response(
        event_page_payload,
        event_id=EVENT_ID,
        tab="player-points",
    )

    assert len(props) == 1
    prop = props[0]
    assert prop["market"] == "points"
    assert prop["player"] == WEMBANYAMA
    assert len(prop["lines"]) == 18
    market_types = {line["market_type"] for line in prop["lines"]}
    assert "TO_SCORE_25+_POINTS" not in market_types
    assert "MONEY_LINE" not in market_types


@pytest.mark.parametrize(
    ("fixture_name", "tab", "market", "player", "main_line"),
    [
        (
            "fd_event_35639109_player_rebounds.json",
            "player-rebounds",
            "rebounds",
            "Victor Wembanyama",
            13.5,
        ),
        (
            "fd_event_35639109_player_assists.json",
            "player-assists",
            "assists",
            "Victor Wembanyama",
            3.5,
        ),
    ],
)
def test_flatten_event_page_core_markets(fixture_name, tab, market, player, main_line):
    payload = json.loads(Path(f"tests/fixtures/{fixture_name}").read_text(encoding="utf-8"))
    props = flatten_event_page_response(payload, event_id=EVENT_ID, tab=tab)

    prop = next(p for p in props if p["player"] == player)
    assert prop["market"] == market
    assert prop["player"] == player
    main = next(line for line in prop["lines"] if line["line"] == main_line)
    assert main["is_main_line"] is True


def test_flatten_event_page_assists_fixture_has_multiple_players():
    payload = json.loads(
        Path("tests/fixtures/fd_event_35639109_player_assists.json").read_text(
            encoding="utf-8"
        )
    )
    props = flatten_event_page_response(
        payload, event_id=EVENT_ID, tab="player-assists"
    )
    players = {prop["player"] for prop in props}
    assert players == {"Victor Wembanyama", "Stephon Castle"}


def test_merge_prop_rows_prefers_main_line(event_page_payload):
    markets = event_page_payload["attachments"]["markets"]
    main = next(
        m for m in markets.values() if m["marketType"] == "PLAYER_A_TOTAL_POINTS"
    )
    alt = next(
        m for m in markets.values() if m["marketType"] == "PLAYER_A_ALT_TOTAL_POINTS"
    )
    line_rows = flatten_player_ou_market(
        main,
        event_id=EVENT_ID,
        tab="player-points",
        canonical_market="points",
    ) + flatten_player_ou_market(
        alt,
        event_id=EVENT_ID,
        tab="player-points",
        canonical_market="points",
    )
    merged = merge_prop_rows(line_rows)
    wemby_255 = next(
        row for row in merged if row["player"] == WEMBANYAMA and row["line"] == 25.5
    )
    assert wemby_255["is_main_line"] is True


@pytest.mark.asyncio
async def test_fetch_and_flatten_event_page(event_page_payload):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=event_page_payload, request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        props = await fetch_and_flatten_event_page(
            client, EVENT_ID, tab="player-points"
        )

    assert len(props) == 1
    assert count_fd_line_rows(props) == 18
