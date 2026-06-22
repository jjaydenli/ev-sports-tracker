"""ESPN (TheScore Bet) scraper — GraphQL persisted-query O/U player props.

Lifecycle (BaseScraper): ``authenticate()`` mints the anonymous JWE once, then
``scrape()`` walks CompetitionPage → Lines section → games → per-event prop sections →
O/U drawers → drawer content, flattening each into the shared master-board schema.
One Startup + one httpx client per run; drawer-content fetches are bounded + jittered
to stay gentle on Cloudflare/bot detection (decision 6).
"""

from __future__ import annotations

import asyncio
import random
from typing import Any

import httpx
from loguru import logger

from config.api_headers import ESPN_CLIENT_HEADERS
from config.espn_markets import (
    canonical_market_for_group_id,
    default_scrape_markets_for_league,
    known_markets_for_league,
)
from scrapers.base_scraper import BaseScraper
from scrapers.sportsbooks.espn_api import (
    ESPNGraphQLClient,
    count_espn_line_rows,
    fetch_drawer_content,
    fetch_games,
    fetch_event_prop_sections,
    fetch_lines_section_id,
    fetch_section_ou_drawers,
    flatten_drawer_content,
)
from scrapers.sportsbooks.espn_auth import ensure_espn_token

DEFAULT_CONCURRENCY = 4
DEFAULT_LEAGUE = "mlb"
_JITTER_SECONDS = 0.25


class ESPNEngine(BaseScraper):
    sportsbook_name = "ESPN"

    def __init__(
        self,
        markets: list[str] | None = None,
        *,
        league: str,
        game_urls: list[str] | None = None,
        concurrency: int = DEFAULT_CONCURRENCY,
    ):
        self.league = league
        self.markets = set(markets or default_scrape_markets_for_league(league))
        self.explicit_game_urls = game_urls or []
        self.concurrency = concurrency
        self._install_id: str | None = None
        self._token: str | None = None
        self._event_start_map: dict[str, str] = {}
        self._event_game_map: dict[str, str] = {}

    async def authenticate(self) -> str | None:
        """Mint (or reuse) the anonymous JWE; returns the token for parity/logging."""
        self._install_id, self._token = await ensure_espn_token()
        return self._token

    async def _resolve_games(self, api: ESPNGraphQLClient) -> list[dict[str, Any]]:
        if self.explicit_game_urls:
            return [{"event_id": "", "canonical_url": url} for url in self.explicit_game_urls]

        section_id = await fetch_lines_section_id(api, self.league)
        if not section_id:
            logger.warning(f"no espn Lines section for {self.league}")
            return []
        games = await fetch_games(api, section_id)
        self._event_start_map = {
            g["event_id"]: g.get("start_time", "") for g in games if g.get("event_id")
        }
        self._event_game_map = {
            g["event_id"]: g.get("game", "") for g in games if g.get("event_id")
        }
        logger.info(f"discovered {len(games)} {self.league.upper()} games from espn slate")
        return games

    async def _scrape_drawer(
        self,
        api: ESPNGraphQLClient,
        semaphore: asyncio.Semaphore,
        *,
        event_id: str,
        drawer: dict[str, str],
    ) -> list[dict[str, Any]]:
        async with semaphore:
            await asyncio.sleep(random.uniform(0, _JITTER_SECONDS))
            payload = await fetch_drawer_content(
                api,
                drawer_id=drawer["drawer_id"],
                group_id=drawer["group_id"],
                section_slug=drawer["section_slug"],
            )
        if not payload:
            return []
        return flatten_drawer_content(
            payload,
            event_id=event_id,
            league=self.league,
            group_id=drawer["group_id"],
            section_slug=drawer["section_slug"],
        )

    async def _scrape_event(
        self,
        api: ESPNGraphQLClient,
        semaphore: asyncio.Semaphore,
        game: dict[str, Any],
    ) -> list[dict[str, Any]]:
        event_id = game.get("event_id", "")
        sections = await fetch_event_prop_sections(
            api, canonical_url=game.get("canonical_url", ""), league=self.league
        )
        drawer_tasks = []
        for section in sections:
            drawers = await fetch_section_ou_drawers(api, section_id=section["section_id"])
            for drawer in drawers:
                if canonical_market_for_group_id(drawer["group_id"]) not in self.markets:
                    continue
                drawer_tasks.append(
                    self._scrape_drawer(api, semaphore, event_id=event_id, drawer=drawer)
                )
        rows: list[dict[str, Any]] = []
        for result in await asyncio.gather(*drawer_tasks, return_exceptions=True):
            if isinstance(result, Exception):
                logger.error(f"espn drawer fetch failed: {result}")
                continue
            rows.extend(result)
        return rows

    async def scrape(self) -> list[dict[str, Any]]:
        unknown = self.markets - known_markets_for_league(self.league)
        if unknown:
            logger.error(f"Unknown ESPN markets: {sorted(unknown)}")
            return []
        if self._token is None:
            await self.authenticate()

        semaphore = asyncio.Semaphore(self.concurrency)
        all_props: list[dict[str, Any]] = []

        async with httpx.AsyncClient(
            headers=ESPN_CLIENT_HEADERS, follow_redirects=True, timeout=15.0
        ) as client:
            api = ESPNGraphQLClient(client, self._install_id or "", self._token or "")
            games = await self._resolve_games(api)
            if not games:
                logger.warning("No ESPN games available to scrape.")
                return []

            results = await asyncio.gather(
                *(self._scrape_event(api, semaphore, game) for game in games),
                return_exceptions=True,
            )

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"espn event scrape failed: {result}")
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

        logger.info(
            f"fetched {len(all_props)} espn props "
            f"({count_espn_line_rows(all_props)} O/U lines) from {len(games)} games"
        )
        return all_props


ESPN_MASTER_BOARD_PATH = "data/processed/espn_master_board.json"


async def run_espn_scrape(
    output_path: str = ESPN_MASTER_BOARD_PATH,
    *,
    markets: list[str] | None = None,
    league: str,
    game_urls: list[str] | None = None,
) -> int:
    """Scrape ESPN and persist the master board; return grouped prop count."""
    engine = ESPNEngine(markets=markets, league=league, game_urls=game_urls)
    props = await engine.run(output_path)
    if not props:
        raise RuntimeError(
            "espn scrape returned no props — check slate, auth, or section/drawer ids"
        )
    logger.success(
        f"espn scrape: saved {len(props)} props "
        f"({count_espn_line_rows(props)} O/U lines) to {output_path}"
    )
    return len(props)


async def main(
    markets: list[str] | None = None,
    league: str = DEFAULT_LEAGUE,
) -> None:
    """Scrape ESPN props and persist the master board.

    ``DEFAULT_LEAGUE`` is the single in-season convenience default for the direct-run
    CLI only (decision 8); the pipeline always passes ``league`` explicitly.
    """
    await run_espn_scrape(markets=markets, league=league)


if __name__ == "__main__":
    asyncio.run(main())
