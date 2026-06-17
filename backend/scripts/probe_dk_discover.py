"""Parallel scan of DraftKings event prop subCategoryIds (ad-hoc debug only).

NOT part of the default add-league-markets workflow — do not run wide/sequential
scans unless the user explicitly requests it. Normal path: user DevTools IDs →
agent verifies each ID individually via probe_dk_subcategories or a single fetch.

Examples::

    python -m scripts.probe_dk_discover --league mlb
    python -m scripts.probe_dk_discover --league mlb --live <live_event_id>
    python -m scripts.probe_dk_discover --league mlb 34267452 --ranges 6580-6760
    python -m scripts.probe_dk_subcategories 34267452 --league mlb
    python -m scripts.probe_dk_subcategories <live_event_id> --league mlb --live --discover
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

import httpx

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from config.api_headers import DK_BASE_HEADERS  # noqa: E402
from config.dk_discovery import (  # noqa: E402
    DK_DISCOVERY_ID_RANGES,
    discovery_id_ranges,
    discovery_output_path,
    parse_id_ranges,
)
from config.dk_subcategories import (  # noqa: E402
    DK_LEAGUE_SLATES,
    build_league_events_url,
)
from scrapers.sportsbooks.dk_subcategory_discovery import (  # noqa: E402
    discover_subcategories,
    pick_live_event_id,
    pick_pregame_event_id,
)


async def resolve_event_id(
    client: httpx.AsyncClient,
    league: str,
    explicit: str | None,
    *,
    live: bool = False,
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
    payload = response.json()
    if live:
        event_id = pick_live_event_id(payload)
        if not event_id:
            raise RuntimeError(
                f"no IN_PROGRESS/STARTED events on DK slate for league={league!r}"
            )
        return event_id
    event_id = pick_pregame_event_id(payload)
    if not event_id:
        raise RuntimeError(f"no NOT_STARTED events on DK slate for league={league!r}")
    return event_id


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
        help="DK event id (default: first NOT_STARTED or --live IN_PROGRESS event)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use first IN_PROGRESS/STARTED event (and include live MLB id ranges)",
    )
    parser.add_argument(
        "--ranges",
        nargs="+",
        metavar="START-END",
        help="Inclusive ID ranges to scan (default: config dk_discovery ranges)",
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
        else discovery_id_ranges(args.league, live=args.live)
    )
    output = args.output or discovery_output_path(args.league, backend_root=BACKEND_ROOT)

    async with httpx.AsyncClient(headers=DK_BASE_HEADERS, timeout=20.0) as client:
        event_id = await resolve_event_id(
            client, args.league, args.event_id, live=args.live
        )

    rows = await discover_subcategories(
        event_id, id_ranges=id_ranges, max_concurrent=args.max_concurrent
    )
    payload = {
        "league": args.league,
        "event_id": event_id,
        "live": args.live,
        "scanned_id_ranges": [list(r) for r in id_ranges],
        "count": len(rows),
        "subcategories": [asdict(row) for row in rows],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    mode = "live" if args.live else "pregame"
    print(
        f"league={args.league}  event={event_id}  mode={mode}  "
        f"discovered={len(rows)}  -> {output}\n"
    )
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
