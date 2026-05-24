import asyncio
from collections.abc import Iterator
from typing import Any

import httpx
from loguru import logger

from config.settings import BETR_BEARER_TOKEN
from scrapers.base_scraper import BaseScraper
from scrapers.dfs.betr.betr_api import fetch_league_upcoming_events


def _build_player_name(player: dict[str, Any]) -> str:
    """Combine first and last name fields into a display name."""
    return f"{player.get('firstName', '')} {player.get('lastName', '')}".strip()


def _is_open_prematch_projection(projection: dict[str, Any]) -> bool:
    """Keep only open, pre-match projections."""
    return projection.get("marketStatus") == "OPENED" and not projection.get("isLive")


def iter_scheduled_events(raw_json: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Yield events with status SCHEDULED from a LeagueUpcomingEvents payload."""
    events = raw_json.get("data", {}).get("getUpcomingEventsV2") or []
    for event in events:
        if event.get("status") == "SCHEDULED":
            yield event


def iter_projections(event: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """
    Walk teams -> players -> projections and yield raw prop context.

    Each yielded dict includes event/player context plus the projection fields.
    """
    event_id = event.get("id", "")
    game = event.get("name", "Unknown Game")

    for team in event.get("teams", []):
        team_name = team.get("name", "")
        for player in team.get("players", []):
            player_id = player.get("id", "")
            player_name = _build_player_name(player)
            if not player_name:
                continue

            for projection in player.get("projections", []):
                if not _is_open_prematch_projection(projection):
                    continue

                market_id = projection.get("marketId")
                if not market_id:
                    continue

                yield {
                    "market_id": market_id,
                    "event_id": event_id,
                    "game": game,
                    "team": team_name,
                    "player_id": player_id,
                    "player": player_name,
                    "label": projection.get("label"),
                    "key": projection.get("key"),
                    "type": projection.get("type"),
                    "value": projection.get("value"),
                    "non_regular_value": projection.get("nonRegularValue"),
                    "market_status": projection.get("marketStatus"),
                    "is_live": projection.get("isLive", False),
                }


def extract_raw_props(raw_json: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten scheduled events into deduplicated raw prop records keyed by market_id."""
    seen_market_ids: set[str] = set()
    props: list[dict[str, Any]] = []

    for event in iter_scheduled_events(raw_json):
        for prop in iter_projections(event):
            market_id = prop["market_id"]
            if market_id in seen_market_ids:
                continue
            seen_market_ids.add(market_id)
            props.append(prop)

    return props


class BetrEngine(BaseScraper):
    sportsbook_name = "Betr"
    default_league = "NBA"

    def __init__(self, bearer_token: str | None = None, league: str | None = None):
        self.bearer_token = bearer_token or BETR_BEARER_TOKEN
        self.league = league or self.default_league

    async def authenticate(self) -> str | None:
        return self.bearer_token

    async def scrape(self) -> list[dict]:
        token = await self.authenticate()
        if not token:
            logger.error("aborting: missing BETR_BEARER_TOKEN")
            return []

        async with httpx.AsyncClient() as client:
            raw_json = await fetch_league_upcoming_events(
                self.league, token, client=client
            )

        if not raw_json:
            logger.warning(f"slate empty: no response for league {self.league}")
            return []

        props = extract_raw_props(raw_json)
        scheduled_count = sum(1 for _ in iter_scheduled_events(raw_json))
        logger.info(
            f"fetched {len(props)} raw props from {scheduled_count} scheduled "
            f"{self.league} events"
        )
        return props


async def main():
    """Orchestrate the Betr data pipeline from slate fetch to disk persistence."""
    logger.info("Starting Betr ingestion...")
    engine = BetrEngine()
    output_path = "data/processed/betr_master_board.json"
    props = await engine.run(output_path)
    logger.success(f"pipeline complete: saved {len(props)} props to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
