"""Verify DraftKings prop subCategoryIds resolve to the expected markets.

This is a *verifier*, not a discoverer. It confirms that a given subCategoryId
returns the market you expect for one event: either the ids already wired into
``config/dk_subcategories.py`` or arbitrary ids you paste with ``--verify``.

Finding *unknown* ids is a separate job: read the ``subCategoryId`` off a stat
tab in browser DevTools, on the ``event/eventSubcategory/v1/markets`` request.
Once you have candidate ids, use ``--verify`` here to confirm each one before
hardcoding it.

examples:
  # verify every configured pregame id for a league resolves
  python -m scripts.verify_dk_subcategories --event-id 30012345 --league mlb

  # verify configured live ids on an in-progress game
  python -m scripts.verify_dk_subcategories --event-id 30012345 --league mlb --live

  # confirm arbitrary ids captured from DevTools (not yet in config)
  python -m scripts.verify_dk_subcategories --event-id 30012345 --verify 6607 17406
"""

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
    DK_NBA_PENDING_STAT_CATEGORIES,
    live_stat_categories_for_league,
    milestone_categories_for_league,
    stat_categories_for_league,
)
from scrapers.sportsbooks.dk_api import (  # noqa: E402
    fetch_event_subcategory_markets,
    infer_canonical_market_from_dk_payload,
)


async def _probe(
    client: httpx.AsyncClient, event_id: str, label: str, prop_subcategory_id: str
) -> None:
    payload = await fetch_event_subcategory_markets(client, event_id, prop_subcategory_id)
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


async def _verify_ids(event_id: str, ids: list[str]) -> None:
    """Probe arbitrary subCategoryIds not (yet) in the config dicts."""
    print(f"Event {event_id}  verifying {len(ids)} pasted id(s)\n")
    async with httpx.AsyncClient(headers=DK_BASE_HEADERS, timeout=15.0) as client:
        for prop_subcategory_id in ids:
            await _probe(client, event_id, "candidate", prop_subcategory_id)


async def _verify_live(event_id: str, league: str) -> None:
    ou_categories = live_stat_categories_for_league(league)
    print(f"Event {event_id}  league={league}  mode=live\n")
    pregame = stat_categories_for_league(league)
    async with httpx.AsyncClient(headers=DK_BASE_HEADERS, timeout=15.0) as client:
        for market in sorted(ou_categories):
            prop_subcategory_id = ou_categories[market]
            if not prop_subcategory_id:
                pregame_id = pregame.get(market, "—")
                print(
                    f"{market:16} {'—':8}  (no live id, capture via DevTools; "
                    f"pregame={pregame_id})"
                )
                continue
            await _probe(client, event_id, market, prop_subcategory_id)


async def _verify_configured(event_id: str, league: str) -> None:
    pregame_categories = stat_categories_for_league(league)
    milestone_categories = milestone_categories_for_league(league)

    print(f"Event {event_id}  league={league}  mode=pregame\n")
    async with httpx.AsyncClient(headers=DK_BASE_HEADERS, timeout=15.0) as client:
        for market, prop_subcategory_id in sorted(pregame_categories.items()):
            if prop_subcategory_id == "TBD":
                print(f"{market:16} {'TBD':8}  (pending — no id)")
                continue
            await _probe(client, event_id, market, prop_subcategory_id)

        if milestone_categories:
            print()
            for market, prop_subcategory_id in sorted(milestone_categories.items()):
                await _probe(client, event_id, f"{market}+", prop_subcategory_id)

    if league == "nba":
        for market in sorted(DK_NBA_PENDING_STAT_CATEGORIES):
            print(f"{market:16} {'—':8}  (pending — no id)")

    if league == "mlb":
        print(
            "\nNote: pregame ids above are wrong for in-game events. "
            "For a live game add --live."
        )


class _HelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Widen the help column so ``--league {nba,mlb,wnba}`` fits on one line."""

    def __init__(self, prog: str) -> None:
        super().__init__(prog, max_help_position=28)


async def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=_HelpFormatter,
    )
    parser.add_argument("--event-id", required=True, dest="event_id", help="DraftKings event id")
    parser.add_argument(
        "--league",
        choices=("nba", "mlb", "wnba"),
        help="Slate key (nba, mlb, or wnba). Required unless --verify is given.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help=(
            "Verify live-event ids (live_stat_categories_for_league) instead of "
            "pregame. Pregame ids are wrong for in-game events. Ignored if "
            "--verify is given."
        ),
    )
    parser.add_argument(
        "--verify",
        nargs="+",
        metavar="ID",
        help=(
            "Verify arbitrary subCategoryIds not yet in the config dicts "
            "(e.g. ids just read off DevTools). Takes precedence over "
            "--live/--league when given."
        ),
    )
    args = parser.parse_args()

    if args.verify:
        await _verify_ids(args.event_id, args.verify)
        return

    if not args.league:
        parser.error("--league is required unless --verify is given")

    if args.live:
        if not live_stat_categories_for_league(args.league):
            parser.error(f"no live subCategoryIds configured for --league {args.league}")
        await _verify_live(args.event_id, args.league)
        return

    await _verify_configured(args.event_id, args.league)


if __name__ == "__main__":
    asyncio.run(main())
