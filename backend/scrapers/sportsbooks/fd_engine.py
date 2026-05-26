"""FanDuel sportsbook scraper via event-page player O/U ladders (main + alt)."""

import asyncio
from typing import Any

import httpx
from loguru import logger

from config.api_headers import FD_BASE_HEADERS
from config.fd_competitions import FD_LEAGUE_SLATES, parse_event_id_from_url
from config.fd_markets import FD_CANONICAL_TO_TAB, tab_for_canonical_market
from scrapers.base_scraper import BaseScraper
from scrapers.sportsbooks.fd_api import (
    fetch_and_flatten_event_page,
    fetch_league_event_ids,
)

DEFAULT_CONCURRENCY = 8
DEFAULT_LEAGUE = "nba"
DEFAULT_MARKETS = ("points",)


def parse_event_ids(
    *,
    event_ids: list[str] | None = None,
    game_urls: list[str] | None = None,
) -> list[str]:
    """Resolve unique FanDuel event IDs from explicit IDs or sportsbook URLs."""
    resolved: list[str] = []
    seen: set[str] = set()

    for event_id in event_ids or []:
        if event_id and event_id not in seen:
            seen.add(event_id)
            resolved.append(event_id)

    for url in game_urls or []:
        event_id = parse_event_id_from_url(url)
        if event_id and event_id not in seen:
            seen.add(event_id)
            resolved.append(event_id)

    return resolved


class FanDuelEngine(BaseScraper):
    sportsbook_name = "FanDuel"

    def __init__(
        self,
        event_ids: list[str] | None = None,
        game_urls: list[str] | None = None,
        markets: list[str] | None = None,
        league: str = DEFAULT_LEAGUE,
        concurrency: int = DEFAULT_CONCURRENCY,
    ):
        self.explicit_event_ids = parse_event_ids(
            event_ids=event_ids, game_urls=game_urls
        )
        self.league = league
        self.markets = markets or list(DEFAULT_MARKETS)
        self.concurrency = concurrency

    async def authenticate(self) -> str | None:
        return None

    async def _resolve_event_ids(self, client: httpx.AsyncClient) -> list[str]:
        if self.explicit_event_ids:
            return self.explicit_event_ids

        event_ids = await fetch_league_event_ids(client, self.league)
        logger.info(
            f"discovered {len(event_ids)} {self.league.upper()} events from fanduel slate"
        )
        return event_ids

    def _tabs_for_markets(self) -> list[str]:
        tabs: list[str] = []
        for market in self.markets:
            tab = tab_for_canonical_market(market)
            if not tab:
                logger.error(f"unknown fanduel market: {market}")
                continue
            if tab not in tabs:
                tabs.append(tab)
        return tabs

    async def scrape(self) -> list[dict[str, Any]]:
        tabs = self._tabs_for_markets()
        if not tabs:
            return []

        unknown_markets = set(self.markets) - set(FD_CANONICAL_TO_TAB)
        if unknown_markets:
            logger.error(f"Unknown FanDuel markets: {sorted(unknown_markets)}")
            return []

        semaphore = asyncio.Semaphore(self.concurrency)
        all_props: list[dict[str, Any]] = []

        async with httpx.AsyncClient(
            headers=FD_BASE_HEADERS,
            follow_redirects=True,
            timeout=15.0,
        ) as client:
            event_ids = await self._resolve_event_ids(client)
            if not event_ids:
                logger.warning("No FanDuel event IDs available to scrape.")
                return []

            async def fetch_tab(event_id: str, tab: str) -> list[dict[str, Any]]:
                async with semaphore:
                    return await fetch_and_flatten_event_page(
                        client, event_id, tab=tab
                    )

            tasks = [
                fetch_tab(event_id, tab)
                for event_id in event_ids
                for tab in tabs
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"fanduel fetch failed: {result}")
                continue
            all_props.extend(result)

        logger.info(
            f"fetched {len(all_props)} fanduel props from {len(event_ids)} events "
            f"x {len(tabs)} tabs"
        )
        return all_props


FD_MASTER_BOARD_PATH = "data/processed/fd_master_board.json"


async def run_fd_scrape(
    output_path: str = FD_MASTER_BOARD_PATH,
    *,
    event_ids: list[str] | None = None,
    game_urls: list[str] | None = None,
    markets: list[str] | None = None,
) -> int:
    """Scrape FanDuel and persist the master board; return prop count."""
    engine = FanDuelEngine(
        event_ids=event_ids,
        game_urls=game_urls,
        markets=markets,
    )
    props = await engine.run(output_path)
    if not props:
        raise RuntimeError(
            "fanduel scrape returned no props — check slate, tabs, or in-play filter"
        )
    logger.success(f"fanduel scrape: saved {len(props)} props to {output_path}")
    return len(props)


async def main(
    event_ids: list[str] | None = None,
    game_urls: list[str] | None = None,
    markets: list[str] | None = None,
):
    """Scrape FanDuel props and persist the master board."""
    await run_fd_scrape(
        event_ids=event_ids,
        game_urls=game_urls,
        markets=markets,
    )


if __name__ == "__main__":
    asyncio.run(main())
