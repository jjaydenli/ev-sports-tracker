"""DraftKings sportsbook markets API client and response flattening."""

from typing import Any

import httpx
from loguru import logger

from config.api_headers import DK_BASE_HEADERS
from config.dk_subcategories import (
    DK_LEAGUE_SLATES,
    DK_STAT_CATEGORIES,
    build_league_events_url,
    build_markets_url,
)
from utils.formatting import normalize_odds_string

DK_SPORTSBOOK = "DraftKings"
MAIN_POINT_LINE_TAG = "MainPointLine"


def parse_american_odds(display_odds: dict[str, Any] | None) -> int | None:
    """Parse DK displayOdds.american into an integer American odds value."""
    if not display_odds:
        return None
    raw = display_odds.get("american")
    if raw is None:
        return None
    try:
        return int(normalize_odds_string(str(raw)))
    except ValueError:
        return None


def _is_main_point_line(selection: dict[str, Any]) -> bool:
    tags = selection.get("tags") or []
    return MAIN_POINT_LINE_TAG in tags


def _selections_by_market(
    selections: list[dict[str, Any]],
) -> dict[str, dict[str, dict[str, Any]]]:
    """Group main-line selections by marketId and outcomeType (Over/Under)."""
    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    for selection in selections:
        if not _is_main_point_line(selection):
            continue
        market_id = selection.get("marketId")
        outcome = selection.get("outcomeType") or selection.get("label")
        if not market_id or outcome not in ("Over", "Under"):
            continue
        grouped.setdefault(market_id, {})[outcome] = selection
    return grouped


def _player_name(selection: dict[str, Any]) -> str | None:
    participants = selection.get("participants") or []
    if not participants:
        return None
    name = participants[0].get("name")
    return str(name) if name else None


def flatten_markets_response(
    payload: dict[str, Any],
    *,
    event_id: str,
    market: str,
) -> list[dict[str, Any]]:
    """Flatten DK markets JSON into master-board prop rows."""
    by_market = _selections_by_market(payload.get("selections") or [])
    props: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, float]] = set()

    for market_id, sides in by_market.items():
        over = sides.get("Over")
        under = sides.get("Under")
        if not over or not under:
            continue

        player = _player_name(over) or _player_name(under)
        line = over.get("points")
        if player is None or line is None:
            continue

        over_odds = parse_american_odds(over.get("displayOdds"))
        under_odds = parse_american_odds(under.get("displayOdds"))
        if over_odds is None or under_odds is None:
            continue

        dedupe_key = (market_id, player, market, float(line))
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        props.append(
            {
                "sportsbook": DK_SPORTSBOOK,
                "event_id": event_id,
                "subcategory_id": DK_STAT_CATEGORIES[market],
                "market_id": market_id,
                "player": player,
                "market": market,
                "line": float(line),
                "over_odds": over_odds,
                "under_odds": under_odds,
                "true_over": over.get("trueOdds"),
                "true_under": under.get("trueOdds"),
            }
        )

    return props


async def fetch_event_subcategory_markets(
    client: httpx.AsyncClient,
    event_id: str,
    subcategory_id: str,
) -> dict[str, Any] | None:
    """Fetch markets JSON for one event and subcategory."""
    url = build_markets_url(event_id, subcategory_id)
    try:
        response = await client.get(url, headers=DK_BASE_HEADERS, timeout=10.0)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:500]
        logger.error(
            f"draftkings api blocked request: {exc.response.status_code} — {body}"
        )
        return None
    except httpx.RequestError as exc:
        logger.error(f"draftkings api request failed: {exc}")
        return None


SCRAPABLE_EVENT_STATUSES = frozenset({"NOT_STARTED"})


def extract_event_ids(
    payload: dict[str, Any],
    *,
    statuses: frozenset[str] | set[str] | None = None,
) -> list[str]:
    """Extract unique event IDs from a league slate response."""
    allowed = statuses if statuses is not None else SCRAPABLE_EVENT_STATUSES
    event_ids: list[str] = []
    seen: set[str] = set()

    for event in payload.get("events") or []:
        event_id = event.get("id")
        if not event_id:
            continue
        event_id = str(event_id)
        if event_id in seen:
            continue
        status = event.get("status")
        if allowed and status not in allowed:
            continue
        seen.add(event_id)
        event_ids.append(event_id)

    return event_ids


async def fetch_league_events(
    client: httpx.AsyncClient,
    league: str = "nba",
) -> dict[str, Any] | None:
    """Fetch the league slate payload that includes events for the given league key."""
    slate = DK_LEAGUE_SLATES.get(league)
    if not slate:
        logger.error(f"unknown draftkings league: {league}")
        return None

    url = build_league_events_url(slate["league_id"], slate["subcategory_id"])
    try:
        response = await client.get(url, headers=DK_BASE_HEADERS, timeout=10.0)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:500]
        logger.error(
            f"draftkings league api blocked request: {exc.response.status_code} — {body}"
        )
        return None
    except httpx.RequestError as exc:
        logger.error(f"draftkings league api request failed: {exc}")
        return None


async def fetch_league_event_ids(
    client: httpx.AsyncClient,
    league: str = "nba",
    *,
    statuses: frozenset[str] | set[str] | None = None,
) -> list[str]:
    """Fetch upcoming event IDs from a league slate page."""
    payload = await fetch_league_events(client, league)
    if not payload:
        return []
    return extract_event_ids(payload, statuses=statuses)


async def fetch_and_flatten_markets(
    client: httpx.AsyncClient,
    event_id: str,
    market: str,
) -> list[dict[str, Any]]:
    """Fetch markets for one category and return flattened master-board rows."""
    subcategory_id = DK_STAT_CATEGORIES[market]
    payload = await fetch_event_subcategory_markets(
        client, event_id, subcategory_id
    )
    if not payload:
        return []
    return flatten_markets_response(payload, event_id=event_id, market=market)
