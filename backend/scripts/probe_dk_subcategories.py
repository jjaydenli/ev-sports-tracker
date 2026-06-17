"""Print selection counts per DraftKings subCategoryId for one event (manual probe)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import httpx

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from config.api_headers import DK_BASE_HEADERS  # noqa: E402
from config.dk_discovery import (  # noqa: E402
    DK_MLB_LIVE_BATTER_MARKETS,
    discovery_id_ranges,
    parse_id_ranges,
)
from config.dk_subcategories import (  # noqa: E402
    DK_MLB_STAT_CATEGORIES,
    DK_NBA_PENDING_STAT_CATEGORIES,
    live_stat_categories_for_league,
    milestone_categories_for_league,
    stat_categories_for_league,
)
from scrapers.sportsbooks.dk_api import (  # noqa: E402
    fetch_event_subcategory_markets,
    infer_canonical_market_from_dk_payload,
)
from scrapers.sportsbooks.dk_subcategory_discovery import (  # noqa: E402
    DiscoveredSubcategory,
    discover_subcategories,
)


async def _probe(event_id: str, label: str, prop_subcategory_id: str) -> None:
    async with httpx.AsyncClient(headers=DK_BASE_HEADERS, timeout=15.0) as client:
        payload = await fetch_event_subcategory_markets(
            client, event_id, prop_subcategory_id
        )
    if not payload:
        print(f"{label:16} {prop_subcategory_id:8}  (no payload)")
        return
    markets = payload.get("markets") or []
    selections = payload.get("selections") or []
    sub_ids = {m.get("subcategoryId") for m in markets if m.get("subcategoryId")}
    inferred = infer_canonical_market_from_dk_payload(payload)
    sample = (markets[0].get("name") if markets else None) or "(no markets)"
    inferred_note = f" -> {inferred}" if inferred else ""
    print(
        f"{label:16} {prop_subcategory_id:8}  markets={len(markets)} "
        f"selections={len(selections)} subcategoryIds={sorted(sub_ids)}"
        f"{inferred_note}  sample={sample!r}"
    )


async def _discover_milestones(
    event_id: str, id_start: int, id_end: int
) -> None:
    """Scan subCategoryId range and print inferred canonical market from DK labels."""
    print(f"Discovering milestone tabs for event {event_id} (ids {id_start}–{id_end})\n")
    async with httpx.AsyncClient(headers=DK_BASE_HEADERS, timeout=15.0) as client:
        for sid in range(id_start, id_end + 1):
            sid_s = str(sid)
            payload = await fetch_event_subcategory_markets(client, event_id, sid_s)
            if not payload:
                continue
            markets = payload.get("markets") or []
            selections = payload.get("selections") or []
            if not markets and not selections:
                continue
            inferred = infer_canonical_market_from_dk_payload(payload)
            sample = markets[0].get("name") if markets else "(selections only)"
            mt = (markets[0].get("marketType") or {}).get("name") if markets else ""
            print(
                f"{sid_s:8}  inferred={inferred or '?':10}  "
                f"markets={len(markets):3}  selections={len(selections):4}  "
                f"type={mt!r}  name={sample!r}"
            )


async def _discover_live_batter(
    event_id: str,
    *,
    league: str,
    id_ranges: tuple[tuple[int, int], ...],
    max_concurrent: int,
) -> None:
    """Scan ID ranges on a live event and print batter O/U subCategoryIds."""
    print(
        f"Discovering live batter O/U subCategoryIds for event {event_id} "
        f"(league={league})\n"
    )
    rows = await discover_subcategories(
        event_id, id_ranges=id_ranges, max_concurrent=max_concurrent
    )
    ou_rows = [row for row in rows if row.has_ou and row.inferred_canonical]
    candidates: dict[str, list[DiscoveredSubcategory]] = {}
    for row in ou_rows:
        canon = row.inferred_canonical
        if canon in DK_MLB_LIVE_BATTER_MARKETS:
            candidates.setdefault(canon, []).append(row)

    by_market: dict[str, DiscoveredSubcategory] = {}
    for market, market_rows in candidates.items():
        pregame_id = DK_MLB_STAT_CATEGORIES.get(market)
        non_pregame = [
            row for row in market_rows if row.prop_subcategory_id != pregame_id
        ]
        by_market[market] = (non_pregame or market_rows)[0]

    pregame = stat_categories_for_league(league)
    print(f"{'market':16} {'pregame':>8}  {'live':>8}  sample")
    print("-" * 60)
    for market in sorted(DK_MLB_LIVE_BATTER_MARKETS):
        live_row = by_market.get(market)
        live_id = live_row.prop_subcategory_id if live_row else "—"
        pregame_id = pregame.get(market, "—")
        sample = live_row.sample_market if live_row else "(not found in scan)"
        changed = live_id != "—" and live_id != pregame_id
        flag = " *" if changed else ""
        print(f"{market:16} {pregame_id:>8}  {live_id:>8}  {sample!r}{flag}")
    print(
        "\n* live id differs from pregame — copy live column into "
        "DK_MLB_LIVE_STAT_CATEGORIES in config/dk_subcategories.py"
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("event_id", help="DraftKings event id")
    parser.add_argument(
        "--league",
        choices=("nba", "mlb"),
        default="nba",
        help="Slate key (nba or mlb)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help=(
            "Probe DK_MLB_LIVE_STAT_CATEGORIES (mlb in-game events). "
            "Without this flag, pregame IDs from DK_MLB_STAT_CATEGORIES are used — "
            "wrong for live games."
        ),
    )
    parser.add_argument(
        "--discover",
        nargs="?",
        const="default",
        metavar="RANGES",
        help=(
            "Scan subCategoryId ranges and print inferred batter O/U ids (mlb + --live). "
            "Optional: space-separated START-END ranges; default includes live MLB ranges."
        ),
    )
    parser.add_argument(
        "--discover-milestones",
        action="store_true",
        help="Scan --id-start..--id-end and print inferred market per non-empty subCategoryId",
    )
    parser.add_argument("--id-start", type=int, default=2716474)
    parser.add_argument("--id-end", type=int, default=2716491)
    parser.add_argument("--max-concurrent", type=int, default=12)
    args = parser.parse_args()

    if args.discover_milestones:
        await _discover_milestones(args.event_id, args.id_start, args.id_end)
        return

    if args.discover:
        if args.league != "mlb" or not args.live:
            parser.error("--discover requires --league mlb --live (in-game event id)")
        if args.discover == "default":
            id_ranges = discovery_id_ranges(args.league, live=True)
        else:
            id_ranges = parse_id_ranges(args.discover.split())
        await _discover_live_batter(
            args.event_id,
            league=args.league,
            id_ranges=id_ranges,
            max_concurrent=args.max_concurrent,
        )
        return

    if args.live:
        if args.league != "mlb":
            parser.error("--live is only supported for --league mlb")
        ou_categories = live_stat_categories_for_league(args.league)
        print(
            f"Event {args.event_id}  league={args.league}  mode=live "
            f"(DK_MLB_LIVE_STAT_CATEGORIES)\n"
        )
        pregame = stat_categories_for_league(args.league)
        for market in sorted(ou_categories):
            prop_subcategory_id = ou_categories[market]
            pregame_id = pregame.get(market, "—")
            if not prop_subcategory_id:
                print(
                    f"{market:16} {'—':8}  (no live id — run with --discover or DevTools; "
                    f"pregame={pregame_id})"
                )
                continue
            await _probe(args.event_id, market, prop_subcategory_id)
        return

    ou_categories = stat_categories_for_league(args.league)
    milestone_categories = milestone_categories_for_league(args.league)

    print(f"Event {args.event_id}  league={args.league}  mode=pregame\n")
    for market, prop_subcategory_id in sorted(ou_categories.items()):
        if prop_subcategory_id == "TBD":
            print(f"{market:16} {'TBD':8}  (pending — no id)")
            continue
        await _probe(args.event_id, market, prop_subcategory_id)

    if milestone_categories:
        print()
        for market, prop_subcategory_id in sorted(milestone_categories.items()):
            await _probe(args.event_id, f"{market}+", prop_subcategory_id)

    if args.league == "nba":
        for market in sorted(DK_NBA_PENDING_STAT_CATEGORIES):
            print(f"{market:16} {'—':8}  (pending — no id)")

    if args.league == "mlb":
        print(
            "\nNote: pregame IDs above are wrong for in-game events. "
            "For a live game use:\n"
            "  python -m scripts.probe_dk_subcategories <live_event_id> "
            "--league mlb --live --discover"
        )


if __name__ == "__main__":
    asyncio.run(main())
