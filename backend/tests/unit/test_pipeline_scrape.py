import json
from unittest.mock import patch

import pytest

from core import pipeline_scrape
from core.pipeline_runner import main
from core.pipeline_scrape import scrape_betr_league

MIXED_PROPS = [
    {"player": "A", "is_live": True},
    {"player": "B", "is_live": False},
    {"player": "C"},
]


class _FakeBetrEngine:
    def __init__(self, league):
        pass

    async def authenticate(self):
        return "token"

    async def scrape(self):
        return list(MIXED_PROPS)


class _FakeSourceFilteredEngine:
    """Mirrors the DK and ESPN contract: live_only drops pregame rows at the source."""

    def __init__(self, league, live_only=False):
        self.live_only = live_only

    async def scrape(self):
        return [p for p in MIXED_PROPS if p.get("is_live") or not self.live_only]


def _no_fanduel(*_args, **_kwargs):
    raise AssertionError("FanDuel engine must not be built in live-only mode")


@patch("core.pipeline_runner._preflight_betr_auth")
def test_cli_live_only_reaches_every_source(_mock_preflight, monkeypatch, tmp_path):
    """Drives the flag from argv through the real wrappers; only the engines are faked."""
    monkeypatch.setattr(pipeline_scrape, "BetrEngine", _FakeBetrEngine)
    monkeypatch.setattr(pipeline_scrape, "DraftKingsEngine", _FakeSourceFilteredEngine)
    monkeypatch.setattr(pipeline_scrape, "ESPNEngine", _FakeSourceFilteredEngine)
    monkeypatch.setattr(pipeline_scrape, "FanDuelEngine", _no_fanduel)

    with pytest.raises(SystemExit) as exc:
        main(["--live-only", "--scrape-only", "--mlb", "--data-dir", str(tmp_path)])

    assert exc.value.code == 0
    sources = json.loads((tmp_path / "scrape_coverage.json").read_text(encoding="utf-8"))["sources"]
    live_row_count = sum(1 for prop in MIXED_PROPS if prop.get("is_live"))
    assert {key: sources[f"{key}:MLB"]["prop_count"] for key in ("betr", "dk", "espn")} == {
        "betr": live_row_count,
        "dk": live_row_count,
        "espn": live_row_count,
    }
    assert (sources["fd:MLB"]["status"], sources["fd:MLB"]["reason"]) == (
        "skipped",
        "no_live_support",
    )


@pytest.mark.asyncio
async def test_betr_default_keeps_all_props(monkeypatch):
    monkeypatch.setattr(pipeline_scrape, "BetrEngine", _FakeBetrEngine)

    result = await scrape_betr_league("nba")

    assert result.prop_count == 3


@pytest.mark.asyncio
async def test_betr_live_only_with_no_live_props_reports_no_events(monkeypatch):
    class _PregameOnly(_FakeBetrEngine):
        async def scrape(self):
            return [{"player": "B", "is_live": False}]

    monkeypatch.setattr(pipeline_scrape, "BetrEngine", _PregameOnly)

    result = await scrape_betr_league("nba", live_only=True)

    assert result.status == "no_events"
