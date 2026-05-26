import asyncio
from collections.abc import Iterator
from typing import Any

import httpx
from loguru import logger

from config.settings import BETR_BEARER_TOKEN
from scrapers.base_scraper import BaseScraper
from scrapers.dfs.betr.betr_api import fetch_league_upcoming_events
from scrapers.dfs.betr.betr_auth import BetrAuthError, ensure_betr_token


def _build_player_name(player: dict[str, Any]) -> str:
    """Combine first and last name fields into a display name."""
    return f"{player.get('firstName', '')} {player.get('lastName', '')}".strip()


def _normalize_key_value_pairs(items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Map GraphQL key/value attribute lists to snake_case dicts."""
    if not items:
        return []
    return [{"key": item.get("key"), "value": item.get("value")} for item in items]


def _normalize_allowed_options(
    options: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Map allowedOptions to snake_case for master board storage."""
    if not options:
        return []
    return [
        {
            "market_option_id": option.get("marketOptionId"),
            "outcome": option.get("outcome"),
        }
        for option in options
    ]


def _normalize_player_recent_stats(
    stats_block: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Map playerRecentStats nested object to snake_case."""
    if not stats_block:
        return None
    return {
        "average_value": stats_block.get("averageValue"),
        "stats": [
            {
                "value": stat.get("value"),
                "matchup_description": stat.get("matchupDescription"),
                "date": stat.get("date"),
            }
            for stat in stats_block.get("stats") or []
        ],
    }


def _normalize_data_feed_source_ids(
    sources: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Map dataFeedSourceIds to snake_case."""
    if not sources:
        return []
    return [{"id": source.get("id"), "source": source.get("source")} for source in sources]


def _normalize_venue_details(venue: dict[str, Any] | None) -> dict[str, Any] | None:
    """Map venueDetails to snake_case."""
    if not venue:
        return None
    return {
        "name": venue.get("name"),
        "city": venue.get("city"),
        "country": venue.get("country"),
    }


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

    Each yielded dict includes event/player context plus projection fields (snake_case).
    """
    event_id = event.get("id", "")
    game = event.get("name", "Unknown Game")
    event_context = {
        "competition_type": event.get("competitionType"),
        "player_structure": event.get("playerStructure"),
        "data_feed_source_ids": _normalize_data_feed_source_ids(
            event.get("dataFeedSourceIds")
        ),
        "venue_details": _normalize_venue_details(event.get("venueDetails")),
        "event_attributes": _normalize_key_value_pairs(event.get("attributes")),
    }

    for team in event.get("teams", []):
        team_name = team.get("name", "")
        team_league = team.get("league")
        team_sport = team.get("sport")
        for player in team.get("players", []):
            player_id = player.get("id", "")
            player_name = _build_player_name(player)
            if not player_name:
                continue

            player_context = {
                "jersey_number": player.get("jerseyNumber"),
                "player_attributes": _normalize_key_value_pairs(player.get("attributes")),
            }

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
                    "team_league": team_league,
                    "team_sport": team_sport,
                    "player_id": player_id,
                    "player": player_name,
                    "label": projection.get("label"),
                    "key": projection.get("key"),
                    "name": projection.get("name"),
                    "type": projection.get("type"),
                    "value": projection.get("value"),
                    "non_regular_value": projection.get("nonRegularValue"),
                    "non_regular_percentage": projection.get("nonRegularPercentage"),
                    "order": projection.get("order"),
                    "current_value": projection.get("currentValue"),
                    "allowed_options": _normalize_allowed_options(
                        projection.get("allowedOptions")
                    ),
                    "player_recent_stats": _normalize_player_recent_stats(
                        projection.get("playerRecentStats")
                    ),
                    "market_status": projection.get("marketStatus"),
                    "is_live": projection.get("isLive", False),
                    **event_context,
                    **player_context,
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
        if self.bearer_token:
            return self.bearer_token
        try:
            return await ensure_betr_token()
        except BetrAuthError as exc:
            logger.error(str(exc))
            return None

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


BETR_MASTER_BOARD_PATH = "data/processed/betr_master_board.json"


async def run_betr_scrape(
    output_path: str = BETR_MASTER_BOARD_PATH,
    *,
    league: str | None = None,
) -> int:
    """Scrape Betr and persist the master board; return prop count."""
    logger.info("Starting Betr ingestion...")
    engine = BetrEngine(league=league)
    props = await engine.run(output_path)
    if not props:
        raise RuntimeError("betr scrape returned no props — check auth and slate")
    logger.success(f"betr scrape: saved {len(props)} props to {output_path}")
    return len(props)


async def main():
    """Orchestrate the Betr data pipeline from slate fetch to disk persistence."""
    await run_betr_scrape()


if __name__ == "__main__":
    asyncio.run(main())
