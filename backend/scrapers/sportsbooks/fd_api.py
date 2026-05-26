"""FanDuel sportsbook API client (league slate / event discovery)."""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from config.api_headers import FD_BASE_HEADERS
from config.fd_competitions import (
    FD_LEAGUE_SLATES,
    build_content_managed_page_url,
    extract_event_ids,
)


async def fetch_league_events(
    client: httpx.AsyncClient,
    league: str = "nba",
) -> dict[str, Any] | None:
    """Fetch the FanDuel custom league page payload (attachments.events)."""
    if league not in FD_LEAGUE_SLATES:
        logger.error(f"unknown fanduel league: {league}")
        return None

    url = build_content_managed_page_url(league)
    try:
        response = await client.get(url, headers=FD_BASE_HEADERS, timeout=15.0)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:500]
        logger.error(
            f"fanduel league api blocked request: {exc.response.status_code} — {body}"
        )
        return None
    except httpx.RequestError as exc:
        logger.error(f"fanduel league api request failed: {exc}")
        return None


async def fetch_league_event_ids(
    client: httpx.AsyncClient,
    league: str = "nba",
    *,
    require_matchup: bool = True,
) -> list[str]:
    """Fetch NBA (or other league) matchup event IDs from the league custom page."""
    payload = await fetch_league_events(client, league)
    if not payload:
        return []

    slate = FD_LEAGUE_SLATES[league]
    return extract_event_ids(
        payload,
        competition_id=slate["competition_id"],
        require_matchup=require_matchup,
    )
