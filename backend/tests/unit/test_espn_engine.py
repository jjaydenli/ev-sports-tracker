import json
from pathlib import Path

import pytest

from config.espn_markets import default_scrape_markets_for_league
from scrapers.sportsbooks.espn_api import count_espn_line_rows
from scrapers.sportsbooks.espn_engine import ESPNEngine

FIX = Path("tests/fixtures")
PITCHER_DRAWER = FIX / "espn_drawer_pitcher_strikeouts.json"
EVENT_ID = "0d4827b4-814e-4761-8f15-73d0c62f5e33"


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
            }
        ]

    async def fake_content(api, *, drawer_id, group_id, section_slug):
        return drawer_payload

    mod = "scrapers.sportsbooks.espn_engine."
    monkeypatch.setattr(mod + "ensure_espn_token", fake_ensure)
    monkeypatch.setattr(mod + "fetch_lines_section_id", fake_section_id)
    monkeypatch.setattr(mod + "fetch_games", fake_games)
    monkeypatch.setattr(mod + "fetch_event_prop_sections", fake_sections)
    monkeypatch.setattr(mod + "fetch_section_ou_drawers", fake_drawers)
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
