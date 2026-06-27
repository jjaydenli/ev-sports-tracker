"""Probe ESPN milestone (UUID-groupId) drawers to see raw market structure.

Walks the full chain up to fetch_section_ou_drawers, but keeps UUID drawers
instead of dropping them. Fetches up to --limit milestone drawer contents and
dumps the raw JSON so we can inspect market type, selection structure, and line
format for stats like singles, doubles, rbis, runs, sb.

Usage:
    cd backend && source .venv/bin/activate
    python scripts/probe_espn_milestone_drawers.py --league mlb --limit 2
"""

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

from config.api_headers import ESPN_CLIENT_HEADERS  # noqa: E402
from config.espn_competitions import extract_event_prop_sections  # noqa: E402
from config.espn_markets import is_ou_group_id  # noqa: E402
from scrapers.sportsbooks.espn_api import (  # noqa: E402
    ESPNGraphQLClient,
    fetch_drawer_content,
    fetch_games,
    fetch_lines_section_id,
)
from scrapers.sportsbooks.espn_auth import ensure_espn_token  # noqa: E402


async def fetch_all_drawers(
    api: ESPNGraphQLClient,
    *,
    section_id: str,
) -> list[dict]:
    """Like fetch_section_ou_drawers but keeps UUID milestone drawers too."""
    payload = await api.request(
        "EventSection",
        {
            "includeFeaturedCarousel": False,
            "includeQuickBetDetails": False,
            "sectionId": section_id,
            "selectedMarketId": None,
        },
    )
    if not payload:
        return []
    section = (payload.get("data") or {}).get("eventSection") or {}
    section_slug = section.get("slug") or ""
    drawers = []
    for child in section.get("sectionChildren") or []:
        if child.get("__typename") != "Drawer":
            continue
        group_id = child.get("groupId") or ""
        is_ou = is_ou_group_id(group_id)
        drawers.append(
            {
                "drawer_id": child.get("id") or "",
                "group_id": group_id,
                "label_text": child.get("labelText") or "",
                "section_slug": section_slug,
                "is_ou": is_ou,
            }
        )
    return drawers


async def run(*, league: str, limit: int) -> int:
    install_id, token = await ensure_espn_token()
    print(f"minted JWE (install_id={install_id})")

    async with httpx.AsyncClient(
        headers=ESPN_CLIENT_HEADERS, follow_redirects=True, timeout=15.0
    ) as client:
        api = ESPNGraphQLClient(client, install_id, token)

        section_id = await fetch_lines_section_id(api, league)
        if not section_id:
            print(f"no Lines section for {league}", file=sys.stderr)
            return 1

        games = await fetch_games(api, section_id)
        active = [g for g in games if str(g.get("status") or "").upper() in {"PRE_GAME", "IN_PLAY"}]
        print(f"{len(active)} active games found\n")
        if not active:
            print("no active games", file=sys.stderr)
            return 1

        game = active[0]
        game_name = game.get("name") or game.get("event_id", "?")
        canonical_url = game.get("canonical_url", "")
        print(f"probing game: {game_name}  url={canonical_url}\n")

        event_page_payload = await api.request("EventPage", {"canonicalUrl": canonical_url})
        sections = extract_event_prop_sections(event_page_payload or {}, league=league)

        milestone_fetched = 0
        for section in sections:
            if milestone_fetched >= limit:
                break
            drawers = await fetch_all_drawers(api, section_id=section["section_id"])
            ou_drawers = [d for d in drawers if d["is_ou"]]
            ms_drawers = [d for d in drawers if not d["is_ou"]]
            print(f"section={section['section_id']}  O/U={len(ou_drawers)}  milestone={len(ms_drawers)}")
            for d in drawers:
                kind = "O/U    " if d["is_ou"] else "MILESTONE"
                print(f"  [{kind}] group_id={d['group_id']!r:<50}  label={d['label_text']!r}")
            print()

            for drawer in ms_drawers:
                if milestone_fetched >= limit:
                    break
                print(f"=== MILESTONE drawer: group_id={drawer['group_id']!r}  label={drawer['label_text']!r} ===")
                payload = await fetch_drawer_content(
                    api,
                    drawer_id=drawer["drawer_id"],
                    group_id=drawer["group_id"],
                    section_slug=drawer["section_slug"],
                )
                if not payload:
                    print("  (no payload returned)\n")
                    continue
                print(json.dumps(payload, indent=2))
                print()
                milestone_fetched += 1

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--league", default="mlb")
    parser.add_argument("--limit", type=int, default=2, help="Number of milestone drawers to fetch")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(league=args.league, limit=args.limit)))


if __name__ == "__main__":
    main()
