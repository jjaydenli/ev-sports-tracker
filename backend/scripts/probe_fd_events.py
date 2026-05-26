"""List FanDuel NBA (or other league) event IDs from the content-managed-page API."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from config.api_headers import FD_BASE_HEADERS, FD_SPORTSBOOK_API_HOST  # noqa: E402
from config.fd_competitions import (  # noqa: E402
    FD_EVENT_TAB_LABELS,
    FD_LEAGUE_SLATES,
    build_event_page_url,
    count_event_page_markets,
    extract_event_summaries,
    parse_event_id_from_url,
)
from scrapers.sportsbooks.fd_api import fetch_event_page, fetch_league_events  # noqa: E402


async def _run(
    *,
    league: str,
    event_id: str | None,
    game_url: str | None,
    tab: str | None,
    include_non_matchup: bool,
    raw: bool,
) -> int:
    if game_url:
        parsed = parse_event_id_from_url(game_url)
        if not parsed:
            print(f"could not parse event id from url: {game_url}", file=sys.stderr)
            return 1
        event_id = parsed
        print(f"parsed event_id={event_id} from url")

    async with httpx.AsyncClient(
        headers=FD_BASE_HEADERS, follow_redirects=True, timeout=15.0
    ) as client:
        if tab:
            if not event_id:
                print("--tab requires --event-id or --game-url", file=sys.stderr)
                return 1
            payload = await fetch_event_page(client, event_id, tab=tab)
            if not payload:
                print("no event-page payload (check host, geo, or FD_API_KEY)", file=sys.stderr)
                return 1
            if raw:
                print(json.dumps(payload, indent=2))
                return 0
            market_count = count_event_page_markets(payload)
            print(
                f"host={FD_SPORTSBOOK_API_HOST} event_id={event_id} "
                f"tab={tab} markets={market_count}"
            )
            return 0

        payload = await fetch_league_events(client, league)

    if not payload:
        print("no payload (check host, geo, or FD_API_KEY)", file=sys.stderr)
        return 1

    if raw:
        print(json.dumps(payload, indent=2))
        return 0

    slate = FD_LEAGUE_SLATES[league]
    summaries = extract_event_summaries(
        payload,
        competition_id=slate["competition_id"],
        require_matchup=not include_non_matchup,
    )

    print(f"host={FD_SPORTSBOOK_API_HOST} league={league} events={len(summaries)}\n")
    for row in summaries:
        print(
            f"{row['event_id']:>10}  {row.get('open_date', ''):<28}  {row.get('name', '')}"
        )

    if event_id:
        match = [s for s in summaries if s["event_id"] == event_id]
        print()
        if match:
            print(f"event {event_id} found on league page")
        else:
            print(
                f"event {event_id} not in filtered list "
                f"(try --include-non-matchup or verify id)"
            )
        print(f"event-page sample url:\n  {build_event_page_url(event_id)}")

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--league", default="nba", choices=sorted(FD_LEAGUE_SLATES))
    parser.add_argument("--event-id", help="Spot-check one event id against the slate")
    parser.add_argument("--game-url", help="Parse event id from a sportsbook event URL")
    parser.add_argument(
        "--include-non-matchup",
        action="store_true",
        help="Include futures/draft/awards titles on the NBA page",
    )
    parser.add_argument("--raw", action="store_true", help="Print full JSON payload")
    parser.add_argument(
        "--tab",
        choices=sorted(FD_EVENT_TAB_LABELS),
        help="Fetch event-page for --event-id and print market count",
    )
    args = parser.parse_args()

    raise SystemExit(
        asyncio.run(
            _run(
                league=args.league,
                event_id=args.event_id,
                game_url=args.game_url,
                tab=args.tab,
                include_non_matchup=args.include_non_matchup,
                raw=args.raw,
            )
        )
    )


if __name__ == "__main__":
    main()
