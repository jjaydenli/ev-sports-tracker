"""Per-source league scrapes for the pipeline (in-memory, no disk writes)."""

from __future__ import annotations

from config.dk_subcategories import (
    DK_LEAGUE_SLATES,
    subcategories_for_league,
)
from config.espn_competitions import ESPN_LEAGUE_SLATES
from config.fd_competitions import FD_LEAGUE_SLATES
from config.pipeline_sources import dk_league_key, normalize_league
from core.scrape_result import ScrapeResult
from scrapers.dfs.betr.betr_engine import BetrEngine
from scrapers.sportsbooks.dk_engine import DraftKingsEngine
from scrapers.sportsbooks.espn_engine import ESPNEngine
from scrapers.sportsbooks.fd_engine import FanDuelEngine


def _only_live(props: list[dict]) -> list[dict]:
    return [prop for prop in props if prop.get("is_live")]


async def scrape_betr_league(league: str, *, live_only: bool = False) -> ScrapeResult:
    """Fetch Betr raw props for one league without persisting."""
    league_key = normalize_league(league)
    try:
        engine = BetrEngine(league=league_key)
        if not await engine.authenticate():
            return ScrapeResult(
                source="betr",
                league=league_key,
                status="failed",
                error="missing or invalid Betr bearer token",
            )
        props = await engine.scrape()
        if live_only:
            props = _only_live(props)
        if not props:
            return ScrapeResult(
                source="betr",
                league=league_key,
                status="no_events",
                prop_count=0,
            )
        return ScrapeResult(
            source="betr",
            league=league_key,
            status="ok",
            prop_count=len(props),
            props=props,
        )
    except Exception as exc:
        return ScrapeResult(
            source="betr",
            league=league_key,
            status="failed",
            error=str(exc),
        )


async def scrape_dk_league(league: str, *, live_only: bool = False) -> ScrapeResult:
    """Fetch DraftKings raw props for one league without persisting."""
    league_key = normalize_league(league)
    dk_slate = dk_league_key(league_key)
    if dk_slate not in DK_LEAGUE_SLATES:
        return ScrapeResult(
            source="dk",
            league=league_key,
            status="skipped",
            reason="not_configured",
        )
    if not subcategories_for_league(dk_slate).pregame.configured_ou:
        return ScrapeResult(
            source="dk",
            league=league_key,
            status="skipped",
            reason="not_configured",
        )
    try:
        engine = DraftKingsEngine(league=dk_slate, live_only=live_only)
        props = await engine.scrape()
        if not props:
            return ScrapeResult(
                source="dk",
                league=league_key,
                status="no_events",
                prop_count=0,
            )
        return ScrapeResult(
            source="dk",
            league=league_key,
            status="ok",
            prop_count=len(props),
            props=props,
        )
    except Exception as exc:
        return ScrapeResult(
            source="dk",
            league=league_key,
            status="failed",
            error=str(exc),
        )


async def scrape_fd_league(league: str, *, live_only: bool = False) -> ScrapeResult:
    """Fetch FanDuel raw props for one league without persisting."""
    league_key = normalize_league(league)
    if live_only:
        # FanDuel rows are never marked live, and live Betr props only match live rows.
        return ScrapeResult(
            source="fd",
            league=league_key,
            status="skipped",
            reason="no_live_support",
        )
    fd_slate = league_key.lower()
    if fd_slate not in FD_LEAGUE_SLATES:
        return ScrapeResult(
            source="fd",
            league=league_key,
            status="skipped",
            reason="not_configured",
        )
    try:
        engine = FanDuelEngine(league=fd_slate)
        props = await engine.scrape()
        if not props:
            return ScrapeResult(
                source="fd",
                league=league_key,
                status="no_events",
                prop_count=0,
            )
        return ScrapeResult(
            source="fd",
            league=league_key,
            status="ok",
            prop_count=len(props),
            props=props,
        )
    except Exception as exc:
        return ScrapeResult(
            source="fd",
            league=league_key,
            status="failed",
            error=str(exc),
        )


async def scrape_espn_league(league: str, *, live_only: bool = False) -> ScrapeResult:
    """Fetch ESPN raw props for one league without persisting."""
    league_key = normalize_league(league)
    espn_slate = league_key.lower()
    if espn_slate not in ESPN_LEAGUE_SLATES:
        return ScrapeResult(
            source="espn",
            league=league_key,
            status="skipped",
            reason="not_configured",
        )
    try:
        engine = ESPNEngine(league=espn_slate, live_only=live_only)
        props = await engine.scrape()
        if not props:
            return ScrapeResult(
                source="espn",
                league=league_key,
                status="no_events",
                prop_count=0,
            )
        return ScrapeResult(
            source="espn",
            league=league_key,
            status="ok",
            prop_count=len(props),
            props=props,
        )
    except Exception as exc:
        return ScrapeResult(
            source="espn",
            league=league_key,
            status="failed",
            error=str(exc),
        )


async def scrape_source_league(
    source: str, league: str, *, live_only: bool = False
) -> ScrapeResult:
    """Dispatch a pipeline source key to its league scraper."""
    if source == "betr":
        return await scrape_betr_league(league, live_only=live_only)
    if source == "dk":
        return await scrape_dk_league(league, live_only=live_only)
    if source == "fd":
        return await scrape_fd_league(league, live_only=live_only)
    if source == "espn":
        return await scrape_espn_league(league, live_only=live_only)
    raise ValueError(f"unknown pipeline source: {source}")
