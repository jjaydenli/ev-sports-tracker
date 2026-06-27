import json
from pathlib import Path

import pytest

from config.espn_markets import default_scrape_markets_for_league
from scrapers.sportsbooks.espn_api import count_espn_line_rows
from scrapers.sportsbooks.espn_engine import ESPNEngine

FIX = Path("tests/fixtures")
PITCHER_DRAWER = FIX / "espn_drawer_pitcher_strikeouts.json"
MILESTONE_DRAWER_SINGLES = FIX / "espn_milestone_drawer_singles.json"
EVENT_ID = "0d4827b4-814e-4761-8f15-73d0c62f5e33"
LIVE_EVENT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
FINAL_EVENT_ID = "ffffffff-0000-1111-2222-333333333333"


def test_mlb_default_markets():
    engine = ESPNEngine(league="mlb")
    assert "strikeouts" in engine.markets
    assert engine.markets == set(default_scrape_markets_for_league("mlb"))


@pytest.mark.asyncio
async def test_authenticate_uses_ensure_token(monkeypatch):
    async def fake_ensure():
        return "install-1", "token-1"

    monkeypatch.setattr("scrapers.sportsbooks.espn_engine.ensure_espn_token", fake_ensure)
    engine = ESPNEngine(league="mlb")
    token = await engine.authenticate()
    assert token == "token-1"
    assert engine._install_id == "install-1"


def _patch_chain(monkeypatch, *, drawer_payload):
    async def fake_ensure():
        return "install-1", "token-1"

    async def fake_section_id(api, league):
        return "Section:lines"

    async def fake_games(api, section_id):
        return [
            {
                "event_id": EVENT_ID,
                "canonical_url": "/sport/.../event/" + EVENT_ID,
                "start_time": "2026-06-22T22:10:00Z",
                "name": "NYY @ DET",
                "game": "NYY@DET",
                "status": "PRE_GAME",
            }
        ]

    async def fake_sections(api, *, canonical_url, league):
        return [{"slug": "pitcher-props", "section_id": "Section:p:Event:" + EVENT_ID}]

    async def fake_drawers(api, *, section_id):
        return [
            {
                "drawer_id": "Drawer:1:PitcherStrikeouts(O/U):Event:" + EVENT_ID,
                "group_id": "PitcherStrikeouts(O/U)",
                "label_text": "Pitcher Strikeouts (O/U)",
                "section_slug": "pitcher-props",
                "kind": "ou",
            }
        ]

    async def fake_content(api, *, drawer_id, group_id, section_slug):
        return drawer_payload

    mod = "scrapers.sportsbooks.espn_engine."
    monkeypatch.setattr(mod + "ensure_espn_token", fake_ensure)
    monkeypatch.setattr(mod + "fetch_lines_section_id", fake_section_id)
    monkeypatch.setattr(mod + "fetch_games", fake_games)
    monkeypatch.setattr(mod + "fetch_event_prop_sections", fake_sections)
    monkeypatch.setattr(mod + "fetch_section_drawers", fake_drawers)
    monkeypatch.setattr(mod + "fetch_drawer_content", fake_content)


@pytest.mark.asyncio
async def test_scrape_pitcher_strikeouts_from_fixture(monkeypatch):
    payload = json.loads(PITCHER_DRAWER.read_text(encoding="utf-8"))
    _patch_chain(monkeypatch, drawer_payload=payload)

    engine = ESPNEngine(markets=["strikeouts"], league="mlb")
    props = await engine.scrape()

    assert {p["market"] for p in props} == {"strikeouts"}
    assert {p["player"] for p in props} == {"Framber Valdez", "Gerrit Cole"}
    assert props[0]["league"] == "MLB"
    assert props[0]["event_start"] == "2026-06-22T22:10:00Z"
    assert count_espn_line_rows(props) == 2


@pytest.mark.asyncio
async def test_scrape_skips_unrequested_market(monkeypatch):
    payload = json.loads(PITCHER_DRAWER.read_text(encoding="utf-8"))
    _patch_chain(monkeypatch, drawer_payload=payload)

    # Only "hits" requested; the pitcher-strikeouts drawer is filtered out before fetch.
    engine = ESPNEngine(markets=["hits"], league="mlb")
    props = await engine.scrape()
    assert props == []


@pytest.mark.asyncio
async def test_scrape_returns_empty_for_unknown_market(monkeypatch):
    async def fake_ensure():
        return "install-1", "token-1"

    monkeypatch.setattr("scrapers.sportsbooks.espn_engine.ensure_espn_token", fake_ensure)
    engine = ESPNEngine(markets=["fantasy_pts"], league="mlb")
    assert await engine.scrape() == []


def _patch_chain_multi_game(monkeypatch, *, drawer_payload):
    """Patch the scrape chain to return one PRE_GAME and one IN_PLAY game."""

    async def fake_ensure():
        return "install-1", "token-1"

    async def fake_section_id(api, league):
        return "Section:lines"

    async def fake_games(api, section_id):
        return [
            {
                "event_id": EVENT_ID,
                "canonical_url": "/sport/.../event/" + EVENT_ID,
                "start_time": "2026-06-22T22:10:00Z",
                "name": "NYY @ DET",
                "game": "NYY@DET",
                "status": "PRE_GAME",
            },
            {
                "event_id": LIVE_EVENT_ID,
                "canonical_url": "/sport/.../event/" + LIVE_EVENT_ID,
                "start_time": "2026-06-22T20:05:00Z",
                "name": "BOS @ NYM",
                "game": "BOS@NYM",
                "status": "IN_PLAY",
            },
        ]

    async def fake_sections(api, *, canonical_url, league):
        event_id = canonical_url.split("/")[-1]
        return [{"slug": "pitcher-props", "section_id": "Section:p:Event:" + event_id}]

    async def fake_drawers(api, *, section_id):
        event_id = section_id.split("Event:")[-1]
        return [
            {
                "drawer_id": f"Drawer:1:PitcherStrikeouts(O/U):Event:{event_id}",
                "group_id": "PitcherStrikeouts(O/U)",
                "label_text": "Pitcher Strikeouts (O/U)",
                "section_slug": "pitcher-props",
                "kind": "ou",
            }
        ]

    async def fake_content(api, *, drawer_id, group_id, section_slug):
        return drawer_payload

    mod = "scrapers.sportsbooks.espn_engine."
    monkeypatch.setattr(mod + "ensure_espn_token", fake_ensure)
    monkeypatch.setattr(mod + "fetch_lines_section_id", fake_section_id)
    monkeypatch.setattr(mod + "fetch_games", fake_games)
    monkeypatch.setattr(mod + "fetch_event_prop_sections", fake_sections)
    monkeypatch.setattr(mod + "fetch_section_drawers", fake_drawers)
    monkeypatch.setattr(mod + "fetch_drawer_content", fake_content)


@pytest.mark.asyncio
async def test_resolve_games_filters_final_status(monkeypatch):
    async def fake_ensure():
        return "install-1", "token-1"

    async def fake_section_id(api, league):
        return "Section:lines"

    async def fake_games(api, section_id):
        return [
            {"event_id": EVENT_ID, "canonical_url": "/event/" + EVENT_ID, "start_time": "", "game": "NYY@DET", "name": "NYY@DET", "status": "PRE_GAME"},
            {"event_id": LIVE_EVENT_ID, "canonical_url": "/event/" + LIVE_EVENT_ID, "start_time": "", "game": "BOS@NYM", "name": "BOS@NYM", "status": "IN_PLAY"},
            {"event_id": FINAL_EVENT_ID, "canonical_url": "/event/" + FINAL_EVENT_ID, "start_time": "", "game": "CHC@LAD", "name": "CHC@LAD", "status": "FINAL"},
        ]

    mod = "scrapers.sportsbooks.espn_engine."
    monkeypatch.setattr(mod + "ensure_espn_token", fake_ensure)
    monkeypatch.setattr(mod + "fetch_lines_section_id", fake_section_id)
    monkeypatch.setattr(mod + "fetch_games", fake_games)

    engine = ESPNEngine(league="mlb")
    await engine.authenticate()
    games = await engine._resolve_games(None)

    event_ids = {g["event_id"] for g in games}
    assert EVENT_ID in event_ids
    assert LIVE_EVENT_ID in event_ids
    assert FINAL_EVENT_ID not in event_ids
    assert len(games) == 2


@pytest.mark.asyncio
async def test_resolve_games_builds_live_map(monkeypatch):
    async def fake_ensure():
        return "install-1", "token-1"

    async def fake_section_id(api, league):
        return "Section:lines"

    async def fake_games(api, section_id):
        return [
            {"event_id": EVENT_ID, "canonical_url": "/event/" + EVENT_ID, "start_time": "", "game": "NYY@DET", "name": "NYY@DET", "status": "PRE_GAME"},
            {"event_id": LIVE_EVENT_ID, "canonical_url": "/event/" + LIVE_EVENT_ID, "start_time": "", "game": "BOS@NYM", "name": "BOS@NYM", "status": "IN_PLAY"},
        ]

    mod = "scrapers.sportsbooks.espn_engine."
    monkeypatch.setattr(mod + "ensure_espn_token", fake_ensure)
    monkeypatch.setattr(mod + "fetch_lines_section_id", fake_section_id)
    monkeypatch.setattr(mod + "fetch_games", fake_games)

    engine = ESPNEngine(league="mlb")
    await engine.authenticate()
    await engine._resolve_games(None)

    assert engine._event_live_map == {LIVE_EVENT_ID: True}
    assert EVENT_ID not in engine._event_live_map


@pytest.mark.asyncio
async def test_scrape_stamps_is_live_for_in_play(monkeypatch):
    payload = json.loads(PITCHER_DRAWER.read_text(encoding="utf-8"))
    _patch_chain_multi_game(monkeypatch, drawer_payload=payload)

    engine = ESPNEngine(markets=["strikeouts"], league="mlb")
    props = await engine.scrape()

    pre_game_props = [p for p in props if p.get("event_id") == EVENT_ID]
    live_props = [p for p in props if p.get("event_id") == LIVE_EVENT_ID]

    assert pre_game_props, "expected PRE_GAME props"
    assert all("is_live" not in p for p in pre_game_props)
    assert live_props, "expected IN_PLAY props"
    assert all(p.get("is_live") is True for p in live_props)


@pytest.mark.asyncio
async def test_explicit_game_urls_bypasses_game_filter(monkeypatch):
    async def fake_ensure():
        return "install-1", "token-1"

    monkeypatch.setattr("scrapers.sportsbooks.espn_engine.ensure_espn_token", fake_ensure)

    engine = ESPNEngine(
        league="mlb",
        game_urls=["/sport/.../event/" + EVENT_ID, "/sport/.../event/" + LIVE_EVENT_ID],
    )
    await engine.authenticate()
    games = await engine._resolve_games(None)

    assert len(games) == 2
    urls = {g["canonical_url"] for g in games}
    assert "/sport/.../event/" + EVENT_ID in urls
    assert "/sport/.../event/" + LIVE_EVENT_ID in urls


@pytest.mark.asyncio
async def test_scrape_milestone_drawer_emits_milestone_rows(monkeypatch):
    """Engine routes milestone drawers through _scrape_milestone_drawer and emits flat rows."""
    payload = json.loads(MILESTONE_DRAWER_SINGLES.read_text(encoding="utf-8"))

    async def fake_ensure():
        return "install-1", "token-1"

    async def fake_section_id(api, league):
        return "Section:lines"

    async def fake_games(api, section_id):
        return [
            {
                "event_id": EVENT_ID,
                "canonical_url": "/sport/.../event/" + EVENT_ID,
                "start_time": "2026-06-27T20:10:00Z",
                "name": "NYY @ DET",
                "game": "NYY@DET",
                "status": "PRE_GAME",
            }
        ]

    async def fake_sections(api, *, canonical_url, league):
        return [{"slug": "batter-props", "section_id": "Section:b:Event:" + EVENT_ID}]

    async def fake_drawers(api, *, section_id):
        return [
            {
                "drawer_id": "Drawer:105477089:a1b2c3d4-0000-0000-0000-000000000001:Event:" + EVENT_ID,
                "group_id": "a1b2c3d4-0000-0000-0000-000000000001",
                "label_text": "Singles",
                "section_slug": "batter-props",
                "kind": "milestone",
            }
        ]

    async def fake_content(api, *, drawer_id, group_id, section_slug):
        return payload

    mod = "scrapers.sportsbooks.espn_engine."
    monkeypatch.setattr(mod + "ensure_espn_token", fake_ensure)
    monkeypatch.setattr(mod + "fetch_lines_section_id", fake_section_id)
    monkeypatch.setattr(mod + "fetch_games", fake_games)
    monkeypatch.setattr(mod + "fetch_event_prop_sections", fake_sections)
    monkeypatch.setattr(mod + "fetch_section_drawers", fake_drawers)
    monkeypatch.setattr(mod + "fetch_drawer_content", fake_content)

    engine = ESPNEngine(markets=["singles"], league="mlb")
    props = await engine.scrape()

    assert props, "expected milestone rows from singles drawer"
    assert all(p["market"] == "singles" for p in props)
    assert all(p["line_kind"] == "milestone" for p in props)
    assert all(p["league"] == "MLB" for p in props)
    assert all(p["event_start"] == "2026-06-27T20:10:00Z" for p in props)
    players = {p["player"] for p in props}
    assert "Jazz Chisholm Jr." in players
    assert "A. Judge" in players
