"""FanDuel league slate IDs and content-managed-page URL builders."""

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
from config.team_abbrev import game_key_from_full_names

# League custom page on sportsbook.fanduel.com/navigation/{league}
FD_LEAGUE_SLATES: dict[str, dict[str, str]] = {
    "nba": {
        "custom_page_id": "nba",
        "competition_id": "10547864",
        "event_type_id": "7522",
    },
    "mlb": {
        "custom_page_id": "mlb",
        "competition_id": "11196870",
        "event_type_id": "7511",
    },
}

# Team @ Team matchups (excludes futures, draft, awards on league custom pages).
MATCHUP_EVENT_NAME_RE = re.compile(r"\s@\s")

# event-page ?tab= slug → layout.tabs[].title (verified on event pages).
FD_EVENT_TAB_LABELS_BY_LEAGUE: dict[str, dict[str, str]] = {
    "nba": {
        "player-points": "Player Points",
        "player-rebounds": "Player Rebounds",
        "player-assists": "Player Assists",
        "same-game-parlay-": "Same Game Parlay\u2122",
    },
    "mlb": {
        "pitcher-props": "Pitcher Props",
        "batter-props": "Batter Props",
        "same-game-parlay-": "Same Game Parlay\u2122",
    },
}

# Back-compat alias (NBA tabs).
FD_EVENT_TAB_LABELS: dict[str, str] = FD_EVENT_TAB_LABELS_BY_LEAGUE["nba"]

EVENT_ID_FROM_URL = re.compile(r"-(\d{6,})(?:\?|$|/)")


def event_tab_labels_for_league(league: str = "nba") -> dict[str, str]:
    return FD_EVENT_TAB_LABELS_BY_LEAGUE[league.lower()]


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
    By default keeps competition matchups (name contains ' @ ').
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


def build_event_start_map(
    payload: dict[str, Any],
    *,
    competition_id: str | None = None,
    require_matchup: bool = True,
) -> dict[str, str]:
    """Map FanDuel event_id -> UTC game start (openDate ISO timestamp)."""
    allowed_ids = set(
        extract_event_ids(
            payload,
            competition_id=competition_id,
            require_matchup=require_matchup,
        )
    )
    attachments = payload.get("attachments") or {}
    events = attachments.get("events") or {}
    mapping: dict[str, str] = {}
    for event_id in allowed_ids:
        event = events.get(event_id) or events.get(int(event_id)) or {}
        open_date = event.get("openDate", "")
        if open_date:
            mapping[str(event_id)] = str(open_date)
    return mapping


def build_event_game_map(
    payload: dict[str, Any],
    *,
    competition_id: str | None = None,
    require_matchup: bool = True,
) -> dict[str, str]:
    """Map FanDuel event_id -> canonical ``AWAY@HOME`` for cross-book game scoping.

    FanDuel events carry only full team names (e.g. ``"Cleveland Guardians (S Bibee)
    @ Chicago White Sox (D Martin)"``); names are resolved to betr-canonical
    abbreviations via ``config.team_abbrev``. Events whose team names are unmapped
    are skipped (logged) and simply carry no ``game`` — degrading to today's behavior
    for that team rather than mismatching.
    """
    from loguru import logger

    allowed_ids = set(
        extract_event_ids(
            payload,
            competition_id=competition_id,
            require_matchup=require_matchup,
        )
    )
    attachments = payload.get("attachments") or {}
    events = attachments.get("events") or {}
    mapping: dict[str, str] = {}
    for event_id in allowed_ids:
        event = events.get(event_id) or events.get(int(event_id)) or {}
        name = str(event.get("name") or "")
        parts = MATCHUP_EVENT_NAME_RE.split(name, maxsplit=1)
        if len(parts) != 2:
            continue
        game = game_key_from_full_names(parts[0], parts[1])
        if game:
            mapping[str(event_id)] = game
        else:
            logger.warning(f"fanduel game-map: unmapped team name in event {name!r}")
    return mapping


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


def count_event_page_markets(payload: dict[str, Any]) -> int:
    """Return the number of markets on an event-page payload."""
    attachments = payload.get("attachments") or {}
    return len(attachments.get("markets") or {})


def extract_event_page_context(
    payload: dict[str, Any],
    *,
    tab: str,
    league: str = "nba",
) -> dict[str, Any]:
    """
    Extract event id and tab context from an event-page response.

    Tab slug (query param) is mapped via league tab labels to layout.tabs titles.
    """
    layout = payload.get("layout") or {}
    page = layout.get("page") or {}
    event_id = str(page.get("eventId") or "")

    tab_title = event_tab_labels_for_league(league).get(tab)
    tabs = layout.get("tabs") or {}
    tab_entry: dict[str, Any] | None = None
    for entry in tabs.values():
        if entry.get("title") == tab_title:
            tab_entry = entry
            break

    return {
        "event_id": event_id,
        "tab": tab,
        "tab_title": tab_title,
        "tab_id": tab_entry.get("id") if tab_entry else None,
        "tab_present": tab_entry is not None,
    }
