"""Fixture contract tests — required-key assertions on fixture JSON files.

Fails loudly when upstream API shape changes silently drop required fields,
rather than letting the parser quietly return empty results.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def _load(name: str) -> dict | list:
    return json.loads((_FIXTURE_DIR / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# DK markets (markets/selections/subscriptionPartials)
# ---------------------------------------------------------------------------

_DK_MARKETS_FILES = [
    "dk_markets_mlb_hits.json",
    "dk_markets_mlb_strikeouts.json",
    "dk_markets_mlb_total_bases.json",
    "dk_markets_mlb_runs.json",
    "dk_markets_mlb_rbi.json",
    "dk_markets_points_34183767.json",
]


@pytest.mark.parametrize("filename", _DK_MARKETS_FILES)
def test_dk_markets_fixture_has_required_keys(filename: str) -> None:
    data = _load(filename)
    assert isinstance(data, dict), f"{filename} should be a JSON object"
    assert "markets" in data, f"{filename} missing 'markets'"
    assert "selections" in data, f"{filename} missing 'selections'"
    assert isinstance(data["markets"], list), f"{filename} 'markets' should be a list"


def test_dk_markets_fixture_markets_have_player_fields() -> None:
    data = _load("dk_markets_mlb_hits.json")
    markets = data["markets"]
    assert len(markets) > 0, "expected at least one market in dk_markets_mlb_hits.json"
    for market in markets[:5]:
        assert "name" in market or "typeName" in market, (
            f"DK market row missing name/typeName: {list(market.keys())}"
        )


# ---------------------------------------------------------------------------
# DK league slate (events)
# ---------------------------------------------------------------------------


def test_dk_league_mlb_events_has_required_keys() -> None:
    data = _load("dk_league_mlb_events.json")
    assert isinstance(data, dict)
    assert "events" in data
    assert isinstance(data["events"], list)


def test_dk_league_mlb_events_with_live_has_events() -> None:
    data = _load("dk_league_mlb_events_with_live.json")
    assert isinstance(data, dict)
    assert "events" in data
    assert isinstance(data["events"], list)


# ---------------------------------------------------------------------------
# FanDuel event pages
# ---------------------------------------------------------------------------

_FD_EVENT_FILES = [
    "fd_event_35639109_player_points.json",
    "fd_event_35639109_player_assists.json",
    "fd_event_35730475_pitcher_props.json",
    "fd_event_35733870_milestones.json",
]


@pytest.mark.parametrize("filename", _FD_EVENT_FILES)
def test_fd_event_fixture_has_required_keys(filename: str) -> None:
    data = _load(filename)
    assert isinstance(data, dict), f"{filename} should be a JSON object"
    assert "layout" in data or "attachments" in data, (
        f"{filename} missing 'layout'/'attachments' — FD API shape drift?"
    )


def test_fd_league_mlb_events_has_layout_or_attachments() -> None:
    data = _load("fd_league_mlb_events.json")
    assert isinstance(data, dict)
    assert "layout" in data or "attachments" in data


# ---------------------------------------------------------------------------
# ESPN GraphQL fixtures
# ---------------------------------------------------------------------------

_ESPN_FILES = [
    "espn_drawer_batter_hits.json",
    "espn_drawer_pitcher_strikeouts.json",
    "espn_event_page.json",
    "espn_lines_games.json",
]


@pytest.mark.parametrize("filename", _ESPN_FILES)
def test_espn_fixture_has_data_key(filename: str) -> None:
    data = _load(filename)
    assert isinstance(data, dict), f"{filename} should be a JSON object"
    assert "data" in data, f"{filename} missing 'data' — ESPN GraphQL shape drift?"


def test_espn_drawer_batter_hits_has_event_drawer() -> None:
    data = _load("espn_drawer_batter_hits.json")
    assert "eventDrawer" in data["data"], "ESPN drawer missing eventDrawer — shape drift?"


# ---------------------------------------------------------------------------
# Betr fixtures
# ---------------------------------------------------------------------------

_BETR_FILES = [
    "betr_mlb_live.json",
    "betr_mlb_pregame.json",
    "betr_wnba_pregame.json",
]


@pytest.mark.parametrize("filename", _BETR_FILES)
def test_betr_fixture_has_data_key(filename: str) -> None:
    data = _load(filename)
    assert isinstance(data, dict), f"{filename} should be a JSON object"
    assert "data" in data, f"{filename} missing 'data' — Betr API shape drift?"


# ---------------------------------------------------------------------------
# DK milestone ladder
# ---------------------------------------------------------------------------


def test_dk_milestone_ladder_fixture_has_required_keys() -> None:
    data = _load("dk_milestone_ladder.json")
    assert "player" in data
    assert "market" in data
    assert "milestone_ladder" in data
    assert isinstance(data["milestone_ladder"], list)
    assert len(data["milestone_ladder"]) > 0
    rung = data["milestone_ladder"][0]
    assert "line" in rung
    assert "over_odds" in rung
