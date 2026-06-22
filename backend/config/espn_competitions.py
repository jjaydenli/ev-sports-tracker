"""ESPN (TheScore Bet) GraphQL slate config + payload traversal helpers.

The read chain is ``CompetitionPage`` (league canonicalUrl → sections) →
``CompetitionPageSectionLinesTabNode`` (Lines section → games) → ``EventPage``
(per-event prop sections) → ``EventSection`` (O/U drawer stubs). The drawer leaf
itself (``EventDrawerContent``) is flattened in ``scrapers/sportsbooks/espn_api.py``.

Traversal is pure (dict in → dict/list out); all I/O lives in the API client.
"""

from __future__ import annotations

from typing import Any

from config.espn_markets import is_ou_group_id, prop_section_slugs_for_league

# Per-league GraphQL slate (decision 8: MLB first, WNBA TBD until its own capture).
ESPN_LEAGUE_SLATES: dict[str, dict[str, str]] = {
    "mlb": {
        "canonical_url": "/sport/baseball/organization/united-states/competition/mlb",
        "lines_section_id": "Section:d9513891-c315-4c16-8554-09d52d3ce9b2",
    },
    "wnba": {
        "canonical_url": "",
        "lines_section_id": "",
    },
}


# ESPN team abbreviations that differ from the betr/DK/FD (anchor) vocabulary used in
# the cross-book match-context key. Map ESPN → canonical so game strings align.
_ESPN_TEAM_ABBR_ALIASES: dict[str, str] = {
    "CWS": "CHW",  # Chicago White Sox — ESPN says CWS, betr/DK/FD say CHW
}


def _canonical_team_abbr(abbr: str) -> str:
    """Normalize an ESPN team abbreviation to the cross-book canonical form."""
    return _ESPN_TEAM_ABBR_ALIASES.get(abbr.upper(), abbr.upper())


def _event_game_key(event: dict[str, Any]) -> str:
    """Build the ``AWAY@HOME`` matchup key (canonical abbrevs) from an event."""
    away = (event.get("awayParticipant") or {}).get("abbreviation") or ""
    home = (event.get("homeParticipant") or {}).get("abbreviation") or ""
    if not away or not home:
        return ""
    return f"{_canonical_team_abbr(away)}@{_canonical_team_abbr(home)}"


def competition_canonical_url(league: str) -> str:
    """Return the CompetitionPage canonicalUrl variable for a league."""
    return ESPN_LEAGUE_SLATES[league.lower()]["canonical_url"]


def lines_section_id(league: str) -> str:
    """Return the captured default Lines section id for a league (may be empty)."""
    return ESPN_LEAGUE_SLATES[league.lower()]["lines_section_id"]


def strip_node_prefix(node_id: str) -> str:
    """Return the UUID from a ``Type:<uuid>`` GraphQL node id (or the id as-is)."""
    return node_id.split(":", 1)[1] if ":" in node_id else node_id


def _iter_dicts(node: Any):
    """Yield every dict nested anywhere under ``node`` (depth-first)."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _iter_dicts(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_dicts(item)


def extract_lines_section_id(competition_payload: dict[str, Any]) -> str | None:
    """Find the default Lines section id in a CompetitionPage response.

    Looks for a ``Section:`` node whose slug is ``lines`` (or archetype
    ``COMPETITION_LINES``). Returns None when absent.
    """
    for node in _iter_dicts(competition_payload.get("data") or {}):
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id.startswith("Section:"):
            continue
        if node.get("slug") == "lines" or node.get("archetype") == "COMPETITION_LINES":
            return node_id
    return None


def extract_games(lines_payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract pre-game events from a CompetitionPageSectionLinesTabNode response.

    Returns ``{event_id, canonical_url, name, game, start_time, status}`` per game,
    deduped by event id. ``event_id`` is the raw UUID (no ``StandardEvent:`` prefix).
    ``game`` is the ``AWAY@HOME`` matchup key used for cross-book context matching.
    """
    node = (lines_payload.get("data") or {}).get("node") or {}
    games: list[dict[str, Any]] = []
    seen: set[str] = set()

    for child in node.get("sectionChildren") or []:
        if child.get("__typename") != "MarketplaceShelf":
            continue
        for card in child.get("marketplaceShelfChildren") or []:
            event = card.get("fallbackEvent") or (card.get("event") or {}).get(
                "fallbackEvent"
            )
            if not isinstance(event, dict):
                continue
            raw_id = event.get("id")
            if not isinstance(raw_id, str) or not raw_id.startswith("StandardEvent:"):
                continue
            event_id = strip_node_prefix(raw_id)
            if event_id in seen:
                continue
            seen.add(event_id)
            canonical_url = (event.get("deepLink") or {}).get("webUrl") or ""
            games.append(
                {
                    "event_id": event_id,
                    "canonical_url": canonical_url,
                    "name": event.get("name") or "",
                    "game": _event_game_key(event),
                    "start_time": event.get("startTime") or "",
                    "status": event.get("status") or "",
                }
            )
    return games


def extract_event_prop_sections(
    event_page_payload: dict[str, Any],
    *,
    league: str,
) -> list[dict[str, str]]:
    """Return ``{slug, section_id}`` for the league's player-prop sections.

    Filters ``data.page.pageChildren`` to the configured prop section slugs
    (``pitcher-props`` / ``batter-props`` for MLB).
    """
    allowed = set(prop_section_slugs_for_league(league))
    page = (event_page_payload.get("data") or {}).get("page") or {}
    sections: list[dict[str, str]] = []
    for child in page.get("pageChildren") or []:
        slug = child.get("slug")
        section_id = child.get("id")
        if slug in allowed and isinstance(section_id, str):
            sections.append({"slug": slug, "section_id": section_id})
    return sections


def extract_section_ou_drawers(
    event_section_payload: dict[str, Any],
) -> list[dict[str, str]]:
    """Return O/U drawer stubs from an EventSection response.

    Keeps only drawers whose ``groupId`` is a literal ``"<Stat>(O/U)"`` (the
    over/under boards); milestone/LIST drawers (UUID groupIds) are dropped.
    Each stub: ``{drawer_id, group_id, label_text, section_slug}``.
    """
    section = (event_section_payload.get("data") or {}).get("eventSection") or {}
    section_slug = section.get("slug") or ""
    drawers: list[dict[str, str]] = []
    for child in section.get("sectionChildren") or []:
        if child.get("__typename") != "Drawer":
            continue
        group_id = child.get("groupId")
        if not is_ou_group_id(group_id):
            continue
        drawers.append(
            {
                "drawer_id": child.get("id") or "",
                "group_id": group_id,
                "label_text": child.get("labelText") or "",
                "section_slug": section_slug,
            }
        )
    return drawers
