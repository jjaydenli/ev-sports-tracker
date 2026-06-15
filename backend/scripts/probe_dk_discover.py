"""Parallel scan of DraftKings event prop subCategoryIds (ad-hoc debug only).

NOT part of the default add-league-markets workflow — do not run wide/sequential
scans unless the user explicitly requests it. Normal path: user DevTools IDs →
agent verifies each ID individually via probe_dk_subcategories or a single fetch.

Examples::

    python -m scripts.probe_dk_discover --league mlb
    python -m scripts.probe_dk_discover --league mlb 34267452 --ranges 6580-6760
    python -m scripts.probe_dk_subcategories 34267452 --league mlb
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from config.api_headers import DK_BASE_HEADERS  # noqa: E402
from config.dk_discovery import (  # noqa: E402
    DK_DISCOVERY_ID_RANGES,
    discovery_output_path,
    parse_id_ranges,
)
from config.dk_subcategories import (  # noqa: E402
    DK_LEAGUE_SLATES,
    build_league_events_url,
)
from scrapers.sportsbooks.dk_api import (  # noqa: E402
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
    ids_to_scan = [
        str(sid)
        for start, end in id_ranges
        for sid in range(start, end + 1)
    ]
    sem = asyncio.Semaphore(max_concurrent)
    async with httpx.AsyncClient(headers=DK_BASE_HEADERS, timeout=15.0) as client:
        results = await asyncio.gather(
            *[_probe_one(client, sem, event_id, sid) for sid in ids_to_scan]
        )
    found = [row for row in results if row is not None]
    found.sort(key=lambda row: int(row.prop_subcategory_id))
    return found


async def resolve_event_id(
    client: httpx.AsyncClient, league: str, explicit: str | None
) -> str:
    if explicit:
        return explicit
    slate = DK_LEAGUE_SLATES.get(league)
    if not slate:
        raise RuntimeError(
            f"no DK_LEAGUE_SLATES entry for {league!r}; add slate ids first"
        )
    url = build_league_events_url(slate["league_id"], slate["slate_subcategory_id"])
    response = await client.get(url)
    response.raise_for_status()
    event_ids = extract_event_ids(response.json())
    if not event_ids:
        raise RuntimeError(f"no NOT_STARTED events on DK slate for league={league!r}")
    return event_ids[0]


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--league",
        choices=sorted(DK_DISCOVERY_ID_RANGES),
        required=True,
        help="DK slate key (must exist in DK_LEAGUE_SLATES for auto event pick)",
    )
    parser.add_argument(
        "event_id",
        nargs="?",
        help="DK event id (default: first NOT_STARTED event on league slate)",
    )
    parser.add_argument(
        "--ranges",
        nargs="+",
        metavar="START-END",
        help="Inclusive ID ranges to scan (default: config dk_discovery.DK_DISCOVERY_ID_RANGES)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write JSON catalog here (default: data/processed/discovery/dk_<league>_prop_subcategories.json)",
    )
    parser.add_argument("--max-concurrent", type=int, default=12)
    args = parser.parse_args()

    id_ranges = (
        parse_id_ranges(args.ranges)
        if args.ranges
        else DK_DISCOVERY_ID_RANGES[args.league]
    )
    output = args.output or discovery_output_path(args.league, backend_root=BACKEND_ROOT)

    async with httpx.AsyncClient(headers=DK_BASE_HEADERS, timeout=20.0) as client:
        event_id = await resolve_event_id(client, args.league, args.event_id)

    rows = await discover_subcategories(
        event_id, id_ranges=id_ranges, max_concurrent=args.max_concurrent
    )
    payload = {
        "league": args.league,
        "event_id": event_id,
        "scanned_id_ranges": [list(r) for r in id_ranges],
        "count": len(rows),
        "subcategories": [asdict(row) for row in rows],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"league={args.league}  event={event_id}  discovered={len(rows)}  -> {output}\n")
    for row in rows:
        ou = "O/U" if row.has_ou else "—"
        canon = row.inferred_canonical or "?"
        print(
            f"{row.prop_subcategory_id:>8}  {ou:3}  "
            f"mkts={row.markets:3}  sels={row.selections:4}  "
            f"canonical={canon!r}  type={row.market_type!r}  "
            f"sample={row.sample_market!r}"
        )


if __name__ == "__main__":
    asyncio.run(main())
