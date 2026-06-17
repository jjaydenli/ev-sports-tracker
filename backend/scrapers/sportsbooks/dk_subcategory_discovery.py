"""Scan DraftKings event prop subCategoryIds (ad-hoc discovery helpers)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx

from config.api_headers import DK_BASE_HEADERS
from scrapers.sportsbooks.dk_api import (
    LIVE_EVENT_STATUSES,
    SCRAPABLE_EVENT_STATUSES,
    _dk_market_label,
    extract_event_ids,
    fetch_event_subcategory_markets,
    infer_canonical_market_from_dk_payload,
)


@dataclass(frozen=True)
class DiscoveredSubcategory:
    prop_subcategory_id: str
    market_type: str
    sample_market: str
    inferred_canonical: str | None
    markets: int
    selections: int
    has_ou: bool


def _has_ou_selections(payload: dict) -> bool:
    for selection in payload.get("selections") or []:
        outcome = selection.get("outcomeType") or selection.get("label")
        if outcome in ("Over", "Under") and selection.get("points") is not None:
            return True
    return False


async def _probe_one(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    event_id: str,
    prop_subcategory_id: str,
) -> DiscoveredSubcategory | None:
    async with sem:
        payload = await fetch_event_subcategory_markets(
            client, event_id, prop_subcategory_id
        )
    if not payload:
        return None
    markets = payload.get("markets") or []
    selections = payload.get("selections") or []
    if not markets and not selections:
        return None
    sample_market = markets[0].get("name") if markets else ""
    market_type = (markets[0].get("marketType") or {}).get("name") if markets else ""
    inferred = infer_canonical_market_from_dk_payload(payload)
    if not inferred and markets:
        inferred = _dk_market_label(markets[0]) or None
    return DiscoveredSubcategory(
        prop_subcategory_id=prop_subcategory_id,
        market_type=str(market_type or ""),
        sample_market=str(sample_market or ""),
        inferred_canonical=inferred,
        markets=len(markets),
        selections=len(selections),
        has_ou=_has_ou_selections(payload),
    )


async def discover_subcategories(
    event_id: str,
    *,
    id_ranges: tuple[tuple[int, int], ...],
    max_concurrent: int = 12,
) -> list[DiscoveredSubcategory]:
    """Parallel scan of subCategoryId ranges for one event."""
    ids_to_scan = [
        str(sid) for start, end in id_ranges for sid in range(start, end + 1)
    ]
    sem = asyncio.Semaphore(max_concurrent)
    async with httpx.AsyncClient(headers=DK_BASE_HEADERS, timeout=15.0) as client:
        results = await asyncio.gather(
            *[_probe_one(client, sem, event_id, sid) for sid in ids_to_scan]
        )
    found = [row for row in results if row is not None]
    found.sort(key=lambda row: int(row.prop_subcategory_id))
    return found


def pick_live_event_id(slate_payload: dict) -> str | None:
    """Return the first in-progress/started event id from a league slate."""
    live_ids = extract_event_ids(slate_payload, statuses=LIVE_EVENT_STATUSES)
    return live_ids[0] if live_ids else None


def pick_pregame_event_id(slate_payload: dict) -> str | None:
    """Return the first not-started event id from a league slate."""
    pregame_ids = extract_event_ids(slate_payload, statuses=SCRAPABLE_EVENT_STATUSES)
    return pregame_ids[0] if pregame_ids else None
