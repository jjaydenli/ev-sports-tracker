"""DraftKings sportsbook scraper via the internal markets API."""

import asyncio
import re
from typing import Any

import httpx
from loguru import logger

from config.api_headers import DK_BASE_HEADERS
from config.dk_subcategories import (
    configured_live_stat_categories_for_league,
    configured_stat_categories_for_league,
    milestone_categories_for_league,
    stat_categories_for_league,
)
from scrapers.base_scraper import BaseScraper
from scrapers.sportsbooks.dk_api import (
    LIVE_EVENT_STATUSES,
    SCRAPABLE_EVENT_STATUSES,
    extract_event_ids,
    fetch_event_all_markets,
    fetch_league_events,
    warm_up_dk_session,
)

DEFAULT_LEAGUE = "nba"
EVENT_ID_FROM_URL = re.compile(r"/event/[^/]+/(\d+)")
# Reuse connections across ~21 parallel subcategory calls per event.
HTTPX_LIMITS = httpx.Limits(max_connections=32, max_keepalive_connections=16)


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
    ):
        self.explicit_event_ids = parse_event_ids(
            event_ids=event_ids, game_urls=game_urls
        )
        self.league = league
        self.stat_categories = stat_categories_for_league(league)
        self.milestone_categories = milestone_categories_for_league(league)
        self.markets = markets or list(self.stat_categories.keys())

    async def authenticate(self) -> str | None:
        return None

    async def _resolve_event_ids(
        self, client: httpx.AsyncClient
    ) -> tuple[list[str], set[str]]:
        """Return (all_event_ids, live_event_ids). For MLB, discovers pregame + live."""
        if self.explicit_event_ids:
            return self.explicit_event_ids, set()

        payload = await fetch_league_events(client, self.league)
        if not payload:
            return [], set()

        if self.league.lower() == "mlb":
            all_ids = extract_event_ids(
                payload, statuses=SCRAPABLE_EVENT_STATUSES | LIVE_EVENT_STATUSES
            )
            live_ids = set(extract_event_ids(payload, statuses=LIVE_EVENT_STATUSES))
        else:
            all_ids = extract_event_ids(payload)
            live_ids = set()

        logger.info(
            f"discovered {len(all_ids)} {self.league.upper()} events from league slate "
            f"({len(live_ids)} live)"
        )
        return all_ids, live_ids

    async def scrape(self) -> list[dict[str, Any]]:
        scrape_categories = configured_stat_categories_for_league(self.league)
        if not scrape_categories:
            logger.error(
                f"no configured DK subCategoryIds for league {self.league!r} "
                f"(probe and update dk_subcategories.py)"
            )
            return []

        unknown_markets = set(self.markets) - set(self.stat_categories)
        if unknown_markets:
            logger.error(f"Unknown DK markets: {sorted(unknown_markets)}")
            return []

        markets_to_scrape = [m for m in self.markets if m in scrape_categories]
        if not markets_to_scrape:
            logger.error(f"no scrapeable DK markets for league {self.league!r}")
            return []

        live_categories = configured_live_stat_categories_for_league(self.league)
        all_props: list[dict[str, Any]] = []

        async with httpx.AsyncClient(
            headers=DK_BASE_HEADERS,
            follow_redirects=True,
            timeout=15.0,
            limits=HTTPX_LIMITS,
        ) as client:
            event_ids, live_event_ids = await self._resolve_event_ids(client)
            if not event_ids:
                logger.warning("No DraftKings event IDs available to scrape.")
                return []

            # League slate already hit during discovery; warm up only for cold starts.
            if self.explicit_event_ids:
                await warm_up_dk_session(client, self.league)

            tasks = []
            task_meta: list[tuple[str, bool]] = []  # (event_id, is_live)
            for event_id in event_ids:
                is_live = event_id in live_event_ids
                if is_live:
                    if not live_categories:
                        continue
                    tasks.append(
                        fetch_event_all_markets(
                            client,
                            event_id,
                            list(live_categories.keys()),
                            stat_categories=live_categories,
                            milestone_categories={},
                        )
                    )
                else:
                    tasks.append(
                        fetch_event_all_markets(
                            client,
                            event_id,
                            markets_to_scrape,
                            stat_categories=scrape_categories,
                            milestone_categories=self.milestone_categories,
                        )
                    )
                task_meta.append((event_id, is_live))

            results = await asyncio.gather(*tasks, return_exceptions=True)

        for (event_id, is_live), result in zip(task_meta, results):
            if isinstance(result, Exception):
                logger.error(f"draftkings fetch failed for {event_id}: {result}")
                continue
            for row in result:
                row["league"] = self.league.upper()
                if is_live:
                    row["is_live"] = True
                all_props.append(row)

        live_count = sum(1 for _, live in task_meta if live)
        logger.info(
            f"fetched {len(all_props)} props from {len(task_meta)} events "
            f"({live_count} live) x {len(markets_to_scrape)} markets"
        )
        return all_props


DK_MASTER_BOARD_PATH = "data/processed/dk_master_board.json"


async def run_dk_scrape(
    output_path: str = DK_MASTER_BOARD_PATH,
    *,
    event_ids: list[str] | None = None,
    game_urls: list[str] | None = None,
    league: str = DEFAULT_LEAGUE,
) -> int:
    """Scrape DraftKings and persist the master board; return prop count."""
    engine = DraftKingsEngine(
        event_ids=event_ids, game_urls=game_urls, league=league
    )
    props = await engine.run(output_path)
    if not props:
        raise RuntimeError("draftkings scrape returned no props — check slate and subcategories")
    logger.success(f"draftkings scrape: saved {len(props)} props to {output_path}")
    return len(props)


async def main(
    event_ids: list[str] | None = None,
    game_urls: list[str] | None = None,
):
    """Scrape DraftKings props and persist the master board."""
    await run_dk_scrape(event_ids=event_ids, game_urls=game_urls)


if __name__ == "__main__":
    asyncio.run(main())
