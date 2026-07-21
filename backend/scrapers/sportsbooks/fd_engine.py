"""FanDuel sportsbook scraper via event-page player O/U ladders (main + alt)."""

import asyncio
from typing import Any

import httpx
from loguru import logger

from config.api_headers import FD_BASE_HEADERS
from config.fd_competitions import (
    FD_LEAGUE_SLATES,
    build_event_game_map,
    build_event_start_map,
    extract_event_ids,
    parse_event_id_from_url,
)
from config.fd_markets import (
    FD_SGP_TAB,
    default_scrape_markets_for_league,
    is_core_ou_market,
    is_extended_ou_market,
    known_markets_for_league,
    tab_for_canonical_market,
)
from scrapers.base_scraper import BaseScraper
from scrapers.sportsbooks.fd_api import (
    count_fd_line_rows,
    fetch_and_flatten_event_page,
    fetch_league_events,
)

DEFAULT_CONCURRENCY = 8
DEFAULT_LEAGUE = "nba"


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
        parsed_id = parse_event_id_from_url(url)
        if parsed_id and parsed_id not in seen:
            seen.add(parsed_id)
            resolved.append(parsed_id)

    return resolved


def scrape_targets_for_markets(
    markets: list[str],
    *,
    league: str = DEFAULT_LEAGUE,
) -> list[tuple[str, set[str] | None]]:
    """
    Map requested canonical markets to event-page tab fetches.

    NBA core stats use dedicated tabs; extended stats share one SGP tab request.
    MLB groups pitcher/batter O/U markets by category tab.
    """
    tab_markets: dict[str, set[str]] = {}
    extended: set[str] = set()

    for market in markets:
        if is_core_ou_market(market, league=league):
            tab = tab_for_canonical_market(market, league=league)
            if tab:
                tab_markets.setdefault(tab, set()).add(market)
        elif is_extended_ou_market(market, league=league):
            extended.add(market)

    targets: list[tuple[str, set[str] | None]] = list(tab_markets.items())
    if extended:
        targets.append((FD_SGP_TAB, extended))
    return targets


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
        self.markets = markets or list(default_scrape_markets_for_league(league))
        self.concurrency = concurrency
        self._event_start_map: dict[str, str] = {}
        self._event_game_map: dict[str, str] = {}

    async def authenticate(self) -> str | None:
        return None

    async def _fetch_league_slate(
        self, client: httpx.AsyncClient
    ) -> tuple[list[str], dict[str, str], dict[str, str]]:
        if self.explicit_event_ids:
            return self.explicit_event_ids, {}, {}

        payload = await fetch_league_events(client, self.league)
        if not payload:
            return [], {}, {}

        slate = FD_LEAGUE_SLATES[self.league]
        event_ids = extract_event_ids(
            payload,
            competition_id=slate["competition_id"],
            require_matchup=True,
        )
        start_map = build_event_start_map(
            payload,
            competition_id=slate["competition_id"],
            require_matchup=True,
        )
        game_map = build_event_game_map(
            payload,
            competition_id=slate["competition_id"],
            require_matchup=True,
        )
        logger.info(
            f"discovered {len(event_ids)} {self.league.upper()} events from fanduel slate"
        )
        return event_ids, start_map, game_map

    async def _resolve_event_ids(self, client: httpx.AsyncClient) -> list[str]:
        event_ids, start_map, game_map = await self._fetch_league_slate(client)
        self._event_start_map = start_map
        self._event_game_map = game_map
        return event_ids

    async def scrape(self) -> list[dict[str, Any]]:
        targets = scrape_targets_for_markets(self.markets, league=self.league)
        if not targets:
            return []

        unknown_markets = set(self.markets) - known_markets_for_league(self.league)
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

            async def fetch_tab(
                event_id: str, tab: str, markets: set[str] | None
            ) -> list[dict[str, Any]]:
                async with semaphore:
                    return await fetch_and_flatten_event_page(
                        client,
                        event_id,
                        tab=tab,
                        markets=markets,
                        league=self.league,
                    )

            tasks = [
                fetch_tab(event_id, tab, markets)
                for event_id in event_ids
                for tab, markets in targets
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"fanduel fetch failed: {result}")
                continue
            if not isinstance(result, list):
                continue
            for row in result:
                row["league"] = self.league.upper()
                event_id = str(row.get("event_id", ""))
                event_start = self._event_start_map.get(event_id, "")
                if event_start:
                    row["event_start"] = event_start
                game = self._event_game_map.get(event_id, "")
                if game:
                    row["game"] = game
                all_props.append(row)

        line_count = count_fd_line_rows(all_props)
        logger.info(
            f"fetched {len(all_props)} fanduel props ({line_count} O/U lines) "
            f"from {len(event_ids)} events x {len(targets)} tab fetches"
        )
        return all_props


FD_MASTER_BOARD_PATH = "data/processed/fd_master_board.json"


async def run_fd_scrape(
    output_path: str = FD_MASTER_BOARD_PATH,
    *,
    event_ids: list[str] | None = None,
    game_urls: list[str] | None = None,
    markets: list[str] | None = None,
    league: str = DEFAULT_LEAGUE,
) -> int:
    """Scrape FanDuel and persist the master board; return grouped prop count."""
    engine = FanDuelEngine(
        event_ids=event_ids,
        game_urls=game_urls,
        markets=markets,
        league=league,
    )
    props = await engine.run(output_path)
    if not props:
        raise RuntimeError(
            "fanduel scrape returned no props — check slate, tabs, or in-play filter"
        )
    logger.success(
        f"fanduel scrape: saved {len(props)} props "
        f"({count_fd_line_rows(props)} O/U lines) to {output_path}"
    )
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
