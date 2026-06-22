"""Live ESPN (TheScore Bet) probe: mint JWE → games → per-event O/U props.

Runs the GraphQL persisted-query chain end to end (CompetitionPage → Lines section →
games → prop sections → O/U drawers → drawer content) and prints flattened O/U rows.
Requires live network + Cloudflare passage; no secrets needed (anonymous JWE is minted).
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

from config.api_headers import ESPN_CLIENT_HEADERS  # noqa: E402
from config.espn_competitions import ESPN_LEAGUE_SLATES  # noqa: E402
from scrapers.sportsbooks.espn_api import (  # noqa: E402
    ESPNGraphQLClient,
    count_espn_line_rows,
    fetch_games,
    fetch_lines_section_id,
)
from scrapers.sportsbooks.espn_auth import ensure_espn_token  # noqa: E402
from scrapers.sportsbooks.espn_engine import ESPNEngine  # noqa: E402


async def _run(*, league: str, limit: int) -> int:
    install_id, token = await ensure_espn_token()
    print(f"minted anonymous JWE (install_id={install_id})")

    async with httpx.AsyncClient(
        headers=ESPN_CLIENT_HEADERS, follow_redirects=True, timeout=15.0
    ) as client:
        api = ESPNGraphQLClient(client, install_id, token)
        section_id = await fetch_lines_section_id(api, league)
        if not section_id:
            print(f"no Lines section for {league}", file=sys.stderr)
            return 1
        games = await fetch_games(api, section_id)
        print(f"league={league} lines_section={section_id} games={len(games)}\n")
        for game in games[:limit]:
            print(f"  {game['event_id']}  {game.get('start_time', ''):<28}  {game.get('name', '')}")

    engine = ESPNEngine(league=league)
    props = await engine.scrape()
    print(f"\nflattened {len(props)} props ({count_espn_line_rows(props)} O/U lines)")
    for prop in props[:limit]:
        lines = ", ".join(
            f"{ln['line']} (o{ln['over_odds']}/u{ln['under_odds']})" for ln in prop["lines"]
        )
        print(f"  {prop['player']:<24} {prop['market']:<14} {lines}")
    return 0 if props else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--league", default="mlb", choices=sorted(ESPN_LEAGUE_SLATES))
    parser.add_argument("--limit", type=int, default=10, help="Rows to print")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(league=args.league, limit=args.limit)))


if __name__ == "__main__":
    main()
