"""DK parser gap tests — covers the uncovered None/edge paths in parsers/dk_parser.py."""

from __future__ import annotations

import json
from pathlib import Path

from parsers.dk_parser import parse_dk_prop, parse_dk_props
from scrapers.sportsbooks.dk_api import flatten_markets_response

_MLB_HITS_FIXTURE = Path("tests/fixtures/dk_markets_mlb_hits.json")


# ---------------------------------------------------------------------------
# parse_dk_prop — valid paths
# ---------------------------------------------------------------------------


def test_parse_dk_prop_returns_normalized_row() -> None:
    raw = {
        "sportsbook": "DraftKings",
        "player": "Aaron Judge",
        "market": "hits",
        "line": 1.5,
        "over_odds": -140,
        "under_odds": 120,
        "is_main_line": True,
        "league": "MLB",
        "event_start": "2026-07-01T18:00:00.000Z",
    }
    prop = parse_dk_prop(raw)
    assert prop is not None
    assert prop["sportsbook"] == "DraftKings"
    assert prop["player"] == "Aaron Judge"
    assert prop["market"] == "hits"
    assert prop["line"] == 1.5
    assert prop["over_odds"] == -140
    assert prop["under_odds"] == 120
    assert prop["league"] == "MLB"
    assert prop["event_start"] == "2026-07-01T18:00:00.000Z"
    assert prop["is_main_line"] is True


def test_parse_dk_prop_league_uppercased() -> None:
    raw = {"player": "x", "market": "hits", "line": 1.5, "league": "mlb"}
    prop = parse_dk_prop(raw)
    assert prop is not None
    assert prop["league"] == "MLB"


def test_parse_dk_prop_is_live_propagated() -> None:
    raw = {"player": "x", "market": "points", "line": 10.5, "is_live": True}
    prop = parse_dk_prop(raw)
    assert prop is not None
    assert prop["is_live"] is True


def test_parse_dk_prop_game_uppercased() -> None:
    raw = {"player": "x", "market": "hits", "line": 0.5, "game": "nyy@bos"}
    prop = parse_dk_prop(raw)
    assert prop is not None
    assert prop["game"] == "NYY@BOS"


def test_parse_dk_prop_defaults_sportsbook() -> None:
    raw = {"player": "x", "market": "hits", "line": 0.5}
    prop = parse_dk_prop(raw)
    assert prop is not None
    assert prop["sportsbook"] == "DraftKings"


# ---------------------------------------------------------------------------
# parse_dk_prop — missing required fields → None
# ---------------------------------------------------------------------------


def test_parse_dk_prop_missing_player_returns_none() -> None:
    assert parse_dk_prop({"market": "hits", "line": 1.5}) is None


def test_parse_dk_prop_missing_market_returns_none() -> None:
    assert parse_dk_prop({"player": "x", "line": 1.5}) is None


def test_parse_dk_prop_missing_line_returns_none() -> None:
    assert parse_dk_prop({"player": "x", "market": "hits"}) is None


def test_parse_dk_prop_none_player_returns_none() -> None:
    assert parse_dk_prop({"player": None, "market": "hits", "line": 1.5}) is None


# ---------------------------------------------------------------------------
# parse_dk_props — list normalisation with fixture
# ---------------------------------------------------------------------------


def test_parse_dk_props_with_mlb_hits_fixture() -> None:
    payload = json.loads(_MLB_HITS_FIXTURE.read_text(encoding="utf-8"))
    raw_props = flatten_markets_response(
        payload,
        event_id="34267452",
        market="hits",
        prop_subcategory_id="1000",
    )
    props = parse_dk_props(raw_props)
    assert len(props) > 0
    for prop in props:
        assert prop["sportsbook"] == "DraftKings"
        assert prop["market"] == "hits"
        assert isinstance(prop["line"], float)
        assert "player" in prop


def test_parse_dk_props_skips_invalid_rows() -> None:
    raw = [
        {"player": "Good Player", "market": "hits", "line": 1.5},
        {"market": "hits", "line": 1.5},  # no player
        {"player": "Another", "line": 1.5},  # no market
    ]
    props = parse_dk_props(raw)
    assert len(props) == 1
    assert props[0]["player"] == "Good Player"


def test_parse_dk_props_empty_input_returns_empty() -> None:
    assert parse_dk_props([]) == []
