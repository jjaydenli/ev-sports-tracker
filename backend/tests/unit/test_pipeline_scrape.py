import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from config.api_headers import DK_LEAGUE_EVENTS_URL
from config.dk_subcategories import DK_NBA_PREGAME_STAT_CATEGORIES
from core import pipeline_scrape
from core.pipeline_runner import main
from core.pipeline_scrape import scrape_betr_league
from scrapers.sportsbooks.dk_api import DkBlockLedger

LIVE_PROP = {"player": "A", "is_live": True}
MIXED_PROPS = [
    LIVE_PROP,
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


class _FlagReportingEngine:
    """Shows whether live_only arrived. test_dk_engine and test_espn_engine cover the filtering."""

    def __init__(self, league, live_only=False):
        self.live_only = live_only
        self.block_ledger = DkBlockLedger()

    async def scrape(self):
        return [LIVE_PROP] if self.live_only else list(MIXED_PROPS)


def _no_fanduel(*_args, **_kwargs):
    raise AssertionError("FanDuel engine must not be built in live-only mode")


@patch("core.pipeline_runner._preflight_betr_auth")
def test_cli_live_only_reaches_every_source(_mock_preflight, monkeypatch, tmp_path):
    """Drives the flag from argv through the real wrappers; only the engines are faked."""
    monkeypatch.setattr(pipeline_scrape, "BetrEngine", _FakeBetrEngine)
    monkeypatch.setattr(pipeline_scrape, "DraftKingsEngine", _FlagReportingEngine)
    monkeypatch.setattr(pipeline_scrape, "ESPNEngine", _FlagReportingEngine)
    monkeypatch.setattr(pipeline_scrape, "FanDuelEngine", _no_fanduel)

    with pytest.raises(SystemExit) as exc:
        main(["--live-only", "--scrape-only", "--mlb", "--data-dir", str(tmp_path)])

    assert exc.value.code == 0
    sources = json.loads((tmp_path / "scrape_coverage.json").read_text(encoding="utf-8"))["sources"]
    assert {key: sources[f"{key}:MLB"]["prop_count"] for key in ("betr", "dk", "espn")} == {
        "betr": 1,
        "dk": 1,
        "espn": 1,
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


_DK_NBA_SLATE = json.loads(
    Path("tests/fixtures/dk_league_nba_events.json").read_text(encoding="utf-8")
)
_DK_POINTS_PAYLOAD = json.loads(
    Path("tests/fixtures/dk_markets_points_34183767.json").read_text(encoding="utf-8")
)


def _dk_transport(
    monkeypatch, *, slate_blocked: bool, ok_subcategory: str | None
) -> set[str]:
    """Route DK traffic through MockTransport; returns the URLs it answered 403 to."""
    blocked_urls: set[str] = set()

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith(DK_LEAGUE_EVENTS_URL) and not slate_blocked:
            return httpx.Response(200, json=_DK_NBA_SLATE, request=request)
        if ok_subcategory is not None and ok_subcategory in url:
            return httpx.Response(200, json=_DK_POINTS_PAYLOAD, request=request)
        blocked_urls.add(url)
        return httpx.Response(403, request=request, text="blocked")

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        "scrapers.sportsbooks.dk_engine.httpx.AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )

    async def no_sleep(_delay):
        return None

    monkeypatch.setattr("scrapers.sportsbooks.dk_api.asyncio.sleep", no_sleep)
    return blocked_urls


@pytest.mark.asyncio
@pytest.mark.parametrize("slate_blocked", [True, False], ids=["slate_blocked", "markets_blocked"])
async def test_dk_fully_blocked_reports_failed_not_no_events(monkeypatch, slate_blocked):
    """A blocked DK scrape must not look like a night with no games."""
    blocked_urls = _dk_transport(monkeypatch, slate_blocked=slate_blocked, ok_subcategory=None)

    result = await pipeline_scrape.scrape_dk_league("nba")

    assert (result.status, result.reason) == ("failed", "blocked")
    assert result.blocked_requests == len(blocked_urls)
    # The slate is the one request that can succeed here.
    assert result.requests == len(blocked_urls) + (0 if slate_blocked else 1)


@pytest.mark.asyncio
async def test_dk_partly_blocked_stays_ok_and_counts_blocks(monkeypatch):
    points_id = DK_NBA_PREGAME_STAT_CATEGORIES["points"]
    blocked_urls = _dk_transport(monkeypatch, slate_blocked=False, ok_subcategory=points_id)

    result = await pipeline_scrape.scrape_dk_league("nba")

    assert result.status == "ok"
    assert result.prop_count > 0
    assert 0 < result.blocked_requests == len(blocked_urls) < result.requests
