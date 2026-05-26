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
from config.dk_subcategories import (  # noqa: E402
    DK_MILESTONE_STAT_CATEGORIES,
    DK_PENDING_STAT_CATEGORIES,
    DK_STAT_CATEGORIES,
)
from scrapers.sportsbooks.dk_api import (  # noqa: E402
    fetch_event_subcategory_markets,
    infer_canonical_market_from_dk_payload,
)


async def _probe(event_id: str, label: str, subcategory_id: str) -> None:
    async with httpx.AsyncClient(headers=DK_BASE_HEADERS, timeout=15.0) as client:
        payload = await fetch_event_subcategory_markets(client, event_id, subcategory_id)
    if not payload:
        print(f"{label:16} {subcategory_id:8}  (no payload)")
        return
    markets = payload.get("markets") or []
    selections = payload.get("selections") or []
    sub_ids = {m.get("subcategoryId") for m in markets if m.get("subcategoryId")}
    inferred = infer_canonical_market_from_dk_payload(payload)
    sample = (markets[0].get("name") if markets else None) or "(no markets)"
    inferred_note = f" -> {inferred}" if inferred else ""
    print(
        f"{label:16} {subcategory_id:8}  markets={len(markets)} "
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


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("event_id", help="DraftKings NBA event id")
    parser.add_argument(
        "--discover-milestones",
        action="store_true",
        help="Scan 2716474–2716491 and print inferred market per non-empty subCategoryId",
    )
    parser.add_argument("--id-start", type=int, default=2716474)
    parser.add_argument("--id-end", type=int, default=2716491)
    args = parser.parse_args()

    if args.discover_milestones:
        await _discover_milestones(args.event_id, args.id_start, args.id_end)
        return

    print(f"Event {args.event_id}\n")
    for market, subcategory_id in sorted(DK_STAT_CATEGORIES.items()):
        await _probe(args.event_id, market, subcategory_id)
    print()
    for market, subcategory_id in sorted(DK_MILESTONE_STAT_CATEGORIES.items()):
        await _probe(args.event_id, f"{market}+", subcategory_id)
    for market in sorted(DK_PENDING_STAT_CATEGORIES):
        print(f"{market:16} {'—':8}  (pending — no id)")


if __name__ == "__main__":
    asyncio.run(main())
