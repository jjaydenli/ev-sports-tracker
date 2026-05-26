"""FanDuel NBA league slate IDs and content-managed-page URL builders."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlencode

from config.api_headers import (
    FD_API_KEY,
    FD_CONTENT_MANAGED_PAGE_PATH,
    FD_EVENT_PAGE_PATH,
    FD_SPORTSBOOK_API_HOST,
)

# League custom page on sportsbook.fanduel.com/navigation/nba
FD_LEAGUE_SLATES: dict[str, dict[str, str]] = {
    "nba": {
        "custom_page_id": "nba",
        "competition_id": "10547864",
        "event_type_id": "7522",
    },
}

# Team @ Team matchups (excludes futures, draft, awards on the NBA custom page).
MATCHUP_EVENT_NAME_RE = re.compile(r"\s@\s")

EVENT_ID_FROM_URL = re.compile(r"-(\d{6,})(?:\?|$|/)")


def build_content_managed_page_url(
    league: str = "nba",
    *,
    include_prices: bool = True,
) -> str:
    """Build the FanDuel league hub URL that returns attachments.events."""
    slate = FD_LEAGUE_SLATES[league]
    query = urlencode(
        {
            "currencyCode": "USD",
            "exchangeLocale": "en_US",
            "includePrices": "true" if include_prices else "false",
            "language": "en",
            "regionCode": "NAMERICA",
            "_ak": FD_API_KEY,
            "page": "CUSTOM",
            "customPageId": slate["custom_page_id"],
        }
    )
    return f"{FD_SPORTSBOOK_API_HOST}{FD_CONTENT_MANAGED_PAGE_PATH}?{query}"


def build_event_page_url(
    event_id: str,
    *,
    tab: str = "player-points",
) -> str:
    """Build the FanDuel per-event markets URL (increment 2: player prop tabs)."""
    query = urlencode(
        {
            "betexRegion": "GBR",
            "capiJurisdiction": "intl",
            "currencyCode": "USD",
            "exchangeLocale": "en_US",
            "includePrices": "true",
            "language": "en",
            "priceHistory": "1",
            "regionCode": "NAMERICA",
            "_ak": FD_API_KEY,
            "eventId": event_id,
            "tab": tab,
        }
    )
    return f"{FD_SPORTSBOOK_API_HOST}{FD_EVENT_PAGE_PATH}?{query}"


def parse_event_id_from_url(url: str) -> str | None:
    """Parse a FanDuel event ID from a sportsbook event URL (trailing numeric segment)."""
    match = EVENT_ID_FROM_URL.search(url)
    return match.group(1) if match else None


def extract_event_ids(
    payload: dict[str, Any],
    *,
    competition_id: str | None = None,
    require_matchup: bool = True,
) -> list[str]:
    """
    Extract unique event IDs from a content-managed-page response.

    League slate events live under attachments.events (dict keyed by eventId).
    By default keeps NBA competition matchups (name contains ' @ ').
    """
    attachments = payload.get("attachments") or {}
    events = attachments.get("events") or {}

    event_ids: list[str] = []
    seen: set[str] = set()

    for key, event in events.items():
        event_id = event.get("eventId") or key
        event_id = str(event_id)
        if event_id in seen:
            continue

        if competition_id is not None:
            if str(event.get("competitionId")) != str(competition_id):
                continue

        name = str(event.get("name") or "")
        if require_matchup and not MATCHUP_EVENT_NAME_RE.search(name):
            continue

        seen.add(event_id)
        event_ids.append(event_id)

    return event_ids


def extract_event_summaries(
    payload: dict[str, Any],
    *,
    competition_id: str | None = None,
    require_matchup: bool = True,
) -> list[dict[str, Any]]:
    """Return event metadata rows for probe / CLI output."""
    attachments = payload.get("attachments") or {}
    events = attachments.get("events") or {}
    allowed_ids = set(
        extract_event_ids(
            payload,
            competition_id=competition_id,
            require_matchup=require_matchup,
        )
    )
    summaries: list[dict[str, Any]] = []
    for event_id in sorted(allowed_ids, key=lambda eid: str(
        (events.get(eid) or events.get(int(eid)) or {}).get("openDate") or eid
    )):
        event = events.get(event_id) or events.get(int(event_id)) or {}
        summaries.append(
            {
                "event_id": event_id,
                "name": event.get("name"),
                "competition_id": event.get("competitionId"),
                "open_date": event.get("openDate"),
            }
        )
    return summaries
