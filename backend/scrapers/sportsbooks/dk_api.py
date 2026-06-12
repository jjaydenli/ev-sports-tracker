"""DraftKings sportsbook markets API client and response flattening."""

import asyncio
import os
import re
from typing import Any

import httpx
from loguru import logger

from config.api_headers import DK_BASE_HEADERS
from config.dk_subcategories import (
    DK_LEAGUE_SLATES,
    DK_MILESTONE_STAT_CATEGORIES,
    DK_STAT_CATEGORIES,
    build_league_events_url,
    build_markets_url,
)
from utils.formatting import normalize_odds_string

DK_SPORTSBOOK = "DraftKings"
MAIN_POINT_LINE_TAG = "MainPointLine"
DK_MARKETS_RETRY_STATUS = frozenset({403, 429})
DK_MARKETS_MAX_ATTEMPTS = 5
DK_MARKETS_RETRY_DELAYS_SEC = (0.5, 1.0, 2.0, 4.0)


def _dk_markets_max_concurrent() -> int:
    raw = os.getenv("DK_MARKETS_MAX_CONCURRENT", "6")
    try:
        value = int(raw)
    except ValueError:
        value = 6
    return max(1, min(value, 16))


_DK_MARKETS_HTTP_SEM = asyncio.Semaphore(_dk_markets_max_concurrent())


def _subcategory_market_label(subcategory_id: str) -> str | None:
    for market, sid in DK_STAT_CATEGORIES.items():
        if sid == subcategory_id:
            return f"ou:{market}"
    for market, sid in DK_MILESTONE_STAT_CATEGORIES.items():
        if sid == subcategory_id:
            return f"milestone:{market}"
    return None


MILESTONE_THRESHOLD_RE = re.compile(r"^(\d+)\+$")

LINE_KIND_OU = "ou"
LINE_KIND_MILESTONE = "milestone"

# Ordered (combo before single-stat). Used to cross-check subCategoryId → market.
_DK_LABEL_MARKET_PATTERNS: tuple[tuple[str, str], ...] = (
    ("pts + reb + ast", "pra"),
    ("points + rebounds + assists", "pra"),
    ("pts + reb", "pts+reb"),
    ("points + rebounds", "pts+reb"),
    ("pts + ast", "pts+ast"),
    ("points + assists", "pts+ast"),
    ("reb + ast", "reb+ast"),
    ("rebounds + assists", "reb+ast"),
    ("steals + blocks", "stl+blk"),
    ("stl + blk", "stl+blk"),
    ("3-pt", "threes"),
    ("3pt", "threes"),
    ("threes", "threes"),
    ("three", "threes"),
    ("steals", "steals"),
    ("blocks", "blocks"),
    ("rebounds", "rebounds"),
    ("assists", "assists"),
    ("points", "points"),
    ("hits + runs + rbis", "h+r+rbi"),
    ("hits runs rbis", "h+r+rbi"),
    ("h+r+rbi", "h+r+rbi"),
    ("singles", "singles"),
)


def _dk_market_label(market: dict[str, Any]) -> str:
    market_type = market.get("marketType") or {}
    return str(market_type.get("name") or market.get("name") or "")


def infer_canonical_market_from_dk_label(label: str) -> str | None:
    """
    Map DraftKings market title / marketType.name text to a canonical market key.

    Combo stats must match before single-stat keywords (e.g. PRA before points).
    """
    text = label.lower().replace("&", "+")
    for needle, market in _DK_LABEL_MARKET_PATTERNS:
        if needle in text:
            return market
    return None


def infer_canonical_market_from_dk_payload(payload: dict[str, Any]) -> str | None:
    """Infer canonical market from the first non-empty market label in a DK payload."""
    for market in payload.get("markets") or []:
        inferred = infer_canonical_market_from_dk_label(_dk_market_label(market))
        if inferred:
            return inferred
    return None


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


def _is_point_line_selection(selection: dict[str, Any]) -> bool:
    if selection.get("points") is None:
        return False
    outcome = selection.get("outcomeType") or selection.get("label")
    return outcome in ("Over", "Under")


def _parse_milestone_threshold(selection: dict[str, Any]) -> int | None:
    """Parse N from milestone labels like '2+' on over-only player props."""
    label = str(selection.get("label") or "").strip()
    match = MILESTONE_THRESHOLD_RE.match(label)
    if match:
        return int(match.group(1))
    outcome = selection.get("outcomeType") or selection.get("label")
    if outcome in ("Over", "Under"):
        return None
    points = selection.get("points")
    if points is not None:
        try:
            value = float(points)
            if value == int(value) and value >= 1:
                return int(value)
        except (TypeError, ValueError):
            pass
    return None


def milestone_threshold_to_line(threshold: int) -> float:
    """Map DK N+ milestone to Betr half-point line (N+ -> line N - 0.5)."""
    return float(threshold) - 0.5


def _selections_by_market_line(
    selections: list[dict[str, Any]],
) -> dict[tuple[str, float], dict[str, Any]]:
    """Group Over/Under selections by marketId and point line (main + alternates)."""
    grouped: dict[tuple[str, float], dict[str, Any]] = {}
    for selection in selections:
        if not _is_point_line_selection(selection):
            continue
        market_id = selection.get("marketId")
        if not market_id:
            continue
        line = float(selection["points"])
        key = (market_id, line)
        entry = grouped.setdefault(
            key,
            {"Over": None, "Under": None, "is_main_line": False},
        )
        outcome = selection.get("outcomeType") or selection.get("label")
        entry[outcome] = selection
        if MAIN_POINT_LINE_TAG in (selection.get("tags") or []):
            entry["is_main_line"] = True
    return grouped


def _milestone_selections_by_market_threshold(
    selections: list[dict[str, Any]],
) -> dict[tuple[str, int], dict[str, Any]]:
    """Group over-only milestone selections by marketId and threshold (N+)."""
    grouped: dict[tuple[str, int], dict[str, Any]] = {}
    for selection in selections:
        threshold = _parse_milestone_threshold(selection)
        if threshold is None:
            continue
        market_id = selection.get("marketId")
        if not market_id:
            continue
        key = (market_id, threshold)
        entry = grouped.setdefault(
            key,
            {"selection": None, "is_main_line": False},
        )
        entry["selection"] = selection
        if MAIN_POINT_LINE_TAG in (selection.get("tags") or []):
            entry["is_main_line"] = True
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
    subcategory_id: str,
) -> list[dict[str, Any]]:
    """Flatten DK markets JSON into master-board prop rows (main + alternate O/U lines)."""
    by_market_line = _selections_by_market_line(payload.get("selections") or [])
    props: list[dict[str, Any]] = []
    seen: set[tuple[str, str, float]] = set()

    for (market_id, line), sides in by_market_line.items():
        over = sides.get("Over")
        under = sides.get("Under")
        if not over or not under:
            continue

        player = _player_name(over) or _player_name(under)
        if player is None:
            continue

        over_odds = parse_american_odds(over.get("displayOdds"))
        under_odds = parse_american_odds(under.get("displayOdds"))
        if over_odds is None or under_odds is None:
            continue

        dedupe_key = (player, market, line)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        props.append(
            {
                "sportsbook": DK_SPORTSBOOK,
                "event_id": event_id,
                "subcategory_id": subcategory_id,
                "market_id": market_id,
                "player": player,
                "market": market,
                "line": line,
                "line_kind": LINE_KIND_OU,
                "over_odds": over_odds,
                "under_odds": under_odds,
                "is_main_line": bool(sides.get("is_main_line")),
                "true_over": over.get("trueOdds"),
                "true_under": under.get("trueOdds"),
            }
        )

    return props


def flatten_milestone_markets_response(
    payload: dict[str, Any],
    *,
    event_id: str,
    market: str,
    subcategory_id: str,
) -> list[dict[str, Any]]:
    """Flatten DK milestone (N+) props into rows comparable to Betr half-point lines."""
    inferred = infer_canonical_market_from_dk_payload(payload)
    if inferred and inferred != market:
        logger.warning(
            f"dk milestone subcategory {subcategory_id} labeled as {market!r} "
            f"but DK market text implies {inferred!r} — fix DK_MILESTONE_STAT_CATEGORIES"
        )

    by_market_threshold = _milestone_selections_by_market_threshold(
        payload.get("selections") or []
    )
    props: list[dict[str, Any]] = []
    seen: set[tuple[str, str, float]] = set()

    for (market_id, threshold), entry in by_market_threshold.items():
        selection = entry.get("selection")
        if not selection:
            continue

        player = _player_name(selection)
        if player is None:
            continue

        over_odds = parse_american_odds(selection.get("displayOdds"))
        if over_odds is None:
            continue

        line = milestone_threshold_to_line(threshold)
        dedupe_key = (player, market, line)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        props.append(
            {
                "sportsbook": DK_SPORTSBOOK,
                "event_id": event_id,
                "subcategory_id": subcategory_id,
                "market_id": market_id,
                "player": player,
                "market": market,
                "line": line,
                "line_kind": LINE_KIND_MILESTONE,
                "milestone_threshold": threshold,
                "over_odds": over_odds,
                "under_odds": None,
                "is_main_line": bool(entry.get("is_main_line")),
                "true_over": selection.get("trueOdds"),
                "true_under": None,
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
    market_label = _subcategory_market_label(subcategory_id)
    last_status: int | None = None

    for attempt in range(1, DK_MARKETS_MAX_ATTEMPTS + 1):
        try:
            async with _DK_MARKETS_HTTP_SEM:
                response = await client.get(
                    url, headers=DK_BASE_HEADERS, timeout=10.0
                )
            last_status = response.status_code
            if response.status_code in DK_MARKETS_RETRY_STATUS:
                if attempt < DK_MARKETS_MAX_ATTEMPTS:
                    delay = DK_MARKETS_RETRY_DELAYS_SEC[attempt - 1]
                    logger.warning(
                        f"draftkings api transient {response.status_code} for "
                        f"{market_label or subcategory_id} (attempt {attempt}/"
                        f"{DK_MARKETS_MAX_ATTEMPTS}); retrying in {delay}s"
                    )
                    await asyncio.sleep(delay)
                    continue
                logger.error(
                    f"draftkings api blocked request after {DK_MARKETS_MAX_ATTEMPTS} "
                    f"attempts: {response.status_code} — {market_label or subcategory_id}"
                )
                return None

            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            last_status = exc.response.status_code
            body = exc.response.text[:500]
            if exc.response.status_code in DK_MARKETS_RETRY_STATUS:
                if attempt < DK_MARKETS_MAX_ATTEMPTS:
                    delay = DK_MARKETS_RETRY_DELAYS_SEC[attempt - 1]
                    logger.warning(
                        f"draftkings api transient {exc.response.status_code} for "
                        f"{market_label or subcategory_id} (attempt {attempt}/"
                        f"{DK_MARKETS_MAX_ATTEMPTS}); retrying in {delay}s"
                    )
                    await asyncio.sleep(delay)
                    continue
                logger.error(
                    f"draftkings api blocked request after {DK_MARKETS_MAX_ATTEMPTS} "
                    f"attempts: {exc.response.status_code} — {body[:200]}"
                )
                return None
            logger.error(
                f"draftkings api blocked request: {exc.response.status_code} — {body}"
            )
            return None
        except httpx.RequestError as exc:
            if attempt < DK_MARKETS_MAX_ATTEMPTS:
                delay = DK_MARKETS_RETRY_DELAYS_SEC[attempt - 1]
                await asyncio.sleep(delay)
                continue
            logger.error(f"draftkings api request failed: {exc}")
            return None

    logger.error(
        f"draftkings api blocked request after {DK_MARKETS_MAX_ATTEMPTS} attempts: "
        f"{last_status} — {market_label or subcategory_id}"
    )
    return None


async def warm_up_dk_session(
    client: httpx.AsyncClient,
    league: str = "nba",
) -> None:
    """Hit the league slate once so Akamai/session state matches browser flow."""
    await fetch_league_events(client, league)


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
    *,
    stat_categories: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Fetch O/U markets for one category and return flattened master-board rows."""
    categories = stat_categories or DK_STAT_CATEGORIES
    subcategory_id = categories[market]
    payload = await fetch_event_subcategory_markets(
        client, event_id, subcategory_id
    )
    if not payload:
        return []
    return flatten_markets_response(
        payload,
        event_id=event_id,
        market=market,
        subcategory_id=subcategory_id,
    )


async def _fetch_and_flatten_milestone_markets(
    client: httpx.AsyncClient,
    event_id: str,
    market: str,
    *,
    milestone_categories: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    milestones = milestone_categories or DK_MILESTONE_STAT_CATEGORIES
    milestone_subcategory_id = milestones.get(market)
    if not milestone_subcategory_id:
        return []
    milestone_payload = await fetch_event_subcategory_markets(
        client, event_id, milestone_subcategory_id
    )
    if not milestone_payload:
        return []
    return flatten_milestone_markets_response(
        milestone_payload,
        event_id=event_id,
        market=market,
        subcategory_id=milestone_subcategory_id,
    )


async def fetch_and_flatten_all_for_market(
    client: httpx.AsyncClient,
    event_id: str,
    market: str,
    *,
    stat_categories: dict[str, str] | None = None,
    milestone_categories: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Fetch O/U and milestone subcategories for one market when configured."""
    ou_props, milestone_props = await asyncio.gather(
        fetch_and_flatten_markets(
            client, event_id, market, stat_categories=stat_categories
        ),
        _fetch_and_flatten_milestone_markets(
            client, event_id, market, milestone_categories=milestone_categories
        ),
    )
    return ou_props + milestone_props


async def fetch_event_all_markets(
    client: httpx.AsyncClient,
    event_id: str,
    markets: list[str] | None = None,
    *,
    stat_categories: dict[str, str] | None = None,
    milestone_categories: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Fetch and flatten all configured O/U and milestone tabs for one event in parallel."""
    categories = stat_categories or DK_STAT_CATEGORIES
    milestones = milestone_categories or DK_MILESTONE_STAT_CATEGORIES
    market_list = markets or list(categories.keys())
    coros = []
    for market in market_list:
        coros.append(
            fetch_and_flatten_markets(
                client, event_id, market, stat_categories=categories
            )
        )
        if market in milestones:
            coros.append(
                _fetch_and_flatten_milestone_markets(
                    client,
                    event_id,
                    market,
                    milestone_categories=milestones,
                )
            )

    results = await asyncio.gather(*coros, return_exceptions=True)
    props: list[dict[str, Any]] = []
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"draftkings market fetch failed for {event_id}: {result}")
            continue
        props.extend(result)
    return props
