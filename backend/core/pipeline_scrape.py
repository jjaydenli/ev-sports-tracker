"""Per-source league scrapes for the pipeline (in-memory, no disk writes)."""

from __future__ import annotations

from config.dk_subcategories import (
    DK_LEAGUE_SLATES,
    configured_stat_categories_for_league,
)
from config.fd_competitions import FD_LEAGUE_SLATES
from config.pipeline_sources import dk_league_key, normalize_league
from core.scrape_result import ScrapeResult
from scrapers.dfs.betr.betr_engine import BetrEngine
from scrapers.sportsbooks.dk_engine import DraftKingsEngine
from scrapers.sportsbooks.fd_engine import FanDuelEngine


async def scrape_betr_league(league: str) -> ScrapeResult:
    """Fetch Betr raw props for one league without persisting."""
    league_key = normalize_league(league)
    try:
        engine = BetrEngine(league=league_key)
        token = await engine.authenticate()
        if not token:
            return ScrapeResult(
                source="betr",
                league=league_key,
                status="failed",
                error="missing or invalid Betr bearer token",
            )
        props = await engine.scrape()
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


async def scrape_dk_league(league: str) -> ScrapeResult:
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
    if not configured_stat_categories_for_league(dk_slate):
        return ScrapeResult(
            source="dk",
            league=league_key,
            status="skipped",
            reason="not_configured",
        )
    try:
        engine = DraftKingsEngine(league=dk_slate)
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


async def scrape_fd_league(league: str) -> ScrapeResult:
    """Fetch FanDuel raw props for one league without persisting."""
    league_key = normalize_league(league)
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


async def scrape_source_league(source: str, league: str) -> ScrapeResult:
    """Dispatch a pipeline source key to its league scraper."""
    if source == "betr":
        return await scrape_betr_league(league)
    if source == "dk":
        return await scrape_dk_league(league)
    if source == "fd":
        return await scrape_fd_league(league)
    raise ValueError(f"unknown pipeline source: {source}")
