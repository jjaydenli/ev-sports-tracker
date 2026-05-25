"""DraftKings sportsbook scraper via the internal markets API."""

import asyncio
import re
from typing import Any

import httpx
from loguru import logger

from config.api_headers import DK_BASE_HEADERS
from config.dk_subcategories import DK_STAT_CATEGORIES
from scrapers.base_scraper import BaseScraper
from scrapers.sportsbooks.dk_api import (
    fetch_and_flatten_markets,
    fetch_league_event_ids,
)

DEFAULT_CONCURRENCY = 12
DEFAULT_LEAGUE = "nba"
EVENT_ID_FROM_URL = re.compile(r"/event/[^/]+/(\d+)")


def extract_event_id_from_url(url: str) -> str | None:
    """Parse a DraftKings event ID from a sportsbook event URL."""
    match = EVENT_ID_FROM_URL.search(url)
    return match.group(1) if match else None


def parse_event_ids(
    *,
    event_ids: list[str] | None = None,
    game_urls: list[str] | None = None,
) -> list[str]:
    """Resolve unique event IDs from explicit IDs or game URLs."""
    resolved: list[str] = []
    seen: set[str] = set()

    for event_id in event_ids or []:
        if event_id and event_id not in seen:
            seen.add(event_id)
            resolved.append(event_id)

    for url in game_urls or []:
        event_id = extract_event_id_from_url(url)
        if event_id and event_id not in seen:
            seen.add(event_id)
            resolved.append(event_id)

    return resolved


class DraftKingsEngine(BaseScraper):
    sportsbook_name = "DraftKings"

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
        self.markets = markets or list(DK_STAT_CATEGORIES.keys())
        self.concurrency = concurrency

    async def authenticate(self) -> str | None:
        return None

    async def _resolve_event_ids(self, client: httpx.AsyncClient) -> list[str]:
        if self.explicit_event_ids:
            return self.explicit_event_ids

        event_ids = await fetch_league_event_ids(client, self.league)
        logger.info(
            f"discovered {len(event_ids)} {self.league.upper()} events from league slate"
        )
        return event_ids

    async def scrape(self) -> list[dict[str, Any]]:
        unknown_markets = set(self.markets) - set(DK_STAT_CATEGORIES)
        if unknown_markets:
            logger.error(f"Unknown DK markets: {sorted(unknown_markets)}")
            return []

        semaphore = asyncio.Semaphore(self.concurrency)
        all_props: list[dict[str, Any]] = []

        async with httpx.AsyncClient(
            headers=DK_BASE_HEADERS,
            follow_redirects=True,
            timeout=15.0,
        ) as client:
            event_ids = await self._resolve_event_ids(client)
            if not event_ids:
                logger.warning("No DraftKings event IDs available to scrape.")
                return []

            async def fetch_category(
                event_id: str, market: str
            ) -> list[dict[str, Any]]:
                async with semaphore:
                    return await fetch_and_flatten_markets(client, event_id, market)

            tasks = [
                fetch_category(event_id, market)
                for event_id in event_ids
                for market in self.markets
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"draftkings fetch failed: {result}")
                continue
            all_props.extend(result)

        logger.info(
            f"fetched {len(all_props)} props from {len(event_ids)} events "
            f"x {len(self.markets)} markets"
        )
        return all_props


async def main(
    event_ids: list[str] | None = None,
    game_urls: list[str] | None = None,
):
    """Scrape DraftKings props and persist the master board."""
    engine = DraftKingsEngine(event_ids=event_ids, game_urls=game_urls)
    output_path = "data/processed/dk_master_board.json"
    props = await engine.run(output_path)
    logger.success(f"pipeline complete: saved {len(props)} props to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
