"""ESPN (TheScore Bet) GraphQL persisted-query client + O/U drawer flatten.

Transport is GraphQL **persisted queries over GET**: the client sends only
``operationName`` + ``variables`` + an ``extensions`` blob carrying the query's
``sha256Hash`` (server-side body). The read chain is CompetitionPage → Lines section →
games → per-event prop sections → O/U drawers → drawer content (the O/U leaf). Flatten
is pure; all I/O goes through :class:`ESPNGraphQLClient`, which re-mints the anonymous
JWE once on a 401/403 (decision 5).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx
from loguru import logger

from config.api_headers import (
    ESPN_GRAPHQL_PERSISTED_PATH,
    ESPN_SPORTSBOOK_API_HOST,
    build_espn_headers,
)
from config.espn_competitions import (
    extract_event_prop_sections,
    extract_games,
    extract_lines_section_id,
    extract_section_drawers,
)
from config.espn_markets import (
    canonical_market_for_group_id,
    canonical_market_for_milestone_label,
)
from config.espn_queries import persisted_query_extensions, persisted_query_hash
from scrapers.sportsbooks.espn_auth import ensure_espn_token
from utils.formatting import normalize_odds_string

ESPN_SPORTSBOOK = "ESPN"
LINE_KIND_OU = "ou"
LINE_KIND_MILESTONE = "milestone"


# --- transport ---------------------------------------------------------------


def persisted_query_url(operation_name: str) -> str:
    """Return the persisted-query GET URL (hash is the trailing path segment)."""
    return (
        f"{ESPN_SPORTSBOOK_API_HOST}{ESPN_GRAPHQL_PERSISTED_PATH}/"
        f"{persisted_query_hash(operation_name)}"
    )


def persisted_query_params(
    operation_name: str,
    variables: dict[str, Any],
) -> dict[str, str]:
    """Return the GET query params for a persisted query (variables + extensions)."""
    return {
        "operationName": operation_name,
        "variables": json.dumps(variables, separators=(",", ":")),
        "extensions": persisted_query_extensions(operation_name),
    }


@dataclass
class ESPNGraphQLClient:
    """Authenticated persisted-query GET client with reactive JWE re-mint.

    Holds the install id + anonymous token for the run; on a 401/403 it re-mints
    once via Startup (stable install id) and retries the same request.
    """

    client: httpx.AsyncClient
    install_id: str
    token: str

    async def request(
        self,
        operation_name: str,
        variables: dict[str, Any],
        *,
        _retried: bool = False,
    ) -> dict[str, Any] | None:
        """Execute one persisted query; re-mint + retry once on 401/403."""
        try:
            response = await self.client.get(
                persisted_query_url(operation_name),
                params=persisted_query_params(operation_name, variables),
                headers=build_espn_headers(self.install_id, self.token),
                timeout=15.0,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in (401, 403) and not _retried:
                logger.info(f"espn {operation_name} got {status}; re-minting token")
                _, self.token = await ensure_espn_token(
                    client=self.client, force_refresh=True
                )
                return await self.request(operation_name, variables, _retried=True)
            logger.error(
                f"espn {operation_name} blocked: {status} — {exc.response.text[:300]}"
            )
            return None
        except httpx.RequestError as exc:
            logger.error(f"espn {operation_name} request failed: {exc}")
            return None


# --- fetch chain (CompetitionPage → drawer content) --------------------------


async def fetch_lines_section_id(api: ESPNGraphQLClient, league: str) -> str | None:
    """Resolve the default Lines section id for a league via CompetitionPage."""
    from config.espn_competitions import competition_canonical_url, lines_section_id

    cached = lines_section_id(league)
    if cached:
        return cached
    payload = await api.request(
        "CompetitionPage", {"canonicalUrl": competition_canonical_url(league)}
    )
    if not payload:
        return None
    return extract_lines_section_id(payload)


async def fetch_games(api: ESPNGraphQLClient, section_id: str) -> list[dict[str, Any]]:
    """Fetch the Lines-section games list (pre-game events)."""
    payload = await api.request(
        "CompetitionPageSectionLinesTabNode",
        {
            "sectionId": section_id,
            # All three are required non-null vars (the server rejects omission/null with
            # VALIDATION_INVALID_TYPE_VARIABLE). American odds match the rest of the pipeline;
            # an empty selectedFilterId means "no filter / all games"; rich-event payload is on.
            "includeRichEvent": True,
            "oddsFormat": "AMERICAN",
            "selectedFilterId": "",
        },
    )
    if not payload:
        return []
    return extract_games(payload)


async def fetch_event_prop_sections(
    api: ESPNGraphQLClient,
    *,
    canonical_url: str,
    league: str,
) -> list[dict[str, str]]:
    """Fetch one event's player-prop sections (pitcher-props / batter-props)."""
    payload = await api.request("EventPage", {"canonicalUrl": canonical_url})
    if not payload:
        return []
    return extract_event_prop_sections(payload, league=league)


async def fetch_section_drawers(
    api: ESPNGraphQLClient,
    *,
    section_id: str,
) -> list[dict[str, str]]:
    """Fetch O/U and milestone drawer stubs for one prop section (single HTTP call)."""
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
    return extract_section_drawers(payload)



def _event_ref_from_drawer_id(drawer_id: str) -> str | None:
    """Extract the ``Event:<uuid>`` ref from ``Drawer:<player>:<groupId>:Event:<uuid>``."""
    marker = "Event:"
    idx = drawer_id.find(marker)
    return drawer_id[idx:] if idx != -1 else None


async def fetch_drawer_content(
    api: ESPNGraphQLClient,
    *,
    drawer_id: str,
    group_id: str,
    section_slug: str,
) -> dict[str, Any] | None:
    """Fetch one O/U drawer's content (the OVER/UNDER markets + selections).

    ``EventDrawerContent`` keys off an ``EventDrawerInput`` of
    ``{sectionSlug, eventId, groupId}`` (there is no ``id`` field) plus a required
    ``oddsFormat``. The ``Event:<uuid>`` ref is embedded in the drawer id.
    """
    event_ref = _event_ref_from_drawer_id(drawer_id)
    if not event_ref:
        return None
    return await api.request(
        "EventDrawerContent",
        {
            "eventDrawerInput": {
                "sectionSlug": section_slug,
                "eventId": event_ref,
                "groupId": group_id,
            },
            "oddsFormat": "AMERICAN",
        },
    )


# --- flatten (pure) ----------------------------------------------------------


def _parse_odds(selection: dict[str, Any]) -> int | None:
    """Parse ``selection.odds.formattedOdds`` ("-155"/"+110"/"Even") into an American int."""
    formatted = ((selection.get("odds") or {}).get("formattedOdds")) or ""
    if not formatted:
        return None
    normalized = str(formatted).strip()
    if normalized.lower() == "even":
        return 100
    try:
        return int(normalize_odds_string(normalized))
    except ValueError:
        return None


def _selection_line(selection: dict[str, Any]) -> float | None:
    """Read the O/U line from the nested ``selection.points.decimalPoints``."""
    points = selection.get("points")
    if not isinstance(points, dict):
        return None
    value = points.get("decimalPoints")
    return float(value) if value is not None else None


def _player_from_market_name(market_name: str, fallback: str | None) -> str | None:
    """Derive the player name from ``"<Player> Total <Stat>"`` (else fallback)."""
    if " Total " in market_name:
        player = market_name.split(" Total ", 1)[0].strip()
        if player:
            return player
    return (fallback or "").strip() or None


def _group_id_from_drawer_id(drawer_id: str) -> str | None:
    """Extract the groupId from ``Drawer:<player>:<groupId>:Event:<eventId>``."""
    parts = drawer_id.split(":")
    return parts[2] if len(parts) >= 3 else None


def flatten_drawer_content(
    payload: dict[str, Any],
    *,
    event_id: str,
    league: str,
    group_id: str | None = None,
    section_slug: str | None = None,
) -> list[dict[str, Any]]:
    """Flatten an EventDrawerContent O/U leaf into grouped master-board props.

    Reads ``data.eventDrawer.drawerChildren[].marketplaceShelfChildren[].markets[]``;
    each ``TOTAL`` market yields one player O/U line (``OVER``/``UNDER`` selections,
    line from ``points.decimalPoints``). Returns one grouped prop per player + market
    with a ``lines`` ladder, matching the shared sharp-book master-board schema.
    """
    drawer = (payload.get("data") or {}).get("eventDrawer") or {}
    if group_id is None:
        group_id = _group_id_from_drawer_id(str(drawer.get("id") or ""))
    canonical_market = canonical_market_for_group_id(group_id)
    if not canonical_market:
        return []

    grouped: dict[tuple[str, str], dict[str, Any]] = {}

    for shelf in drawer.get("drawerChildren") or []:
        for card in shelf.get("marketplaceShelfChildren") or []:
            participant = card.get("participant") or {}
            for market in card.get("markets") or []:
                if str(market.get("type") or "").upper() != "TOTAL":
                    continue
                if str(market.get("status") or "").upper() != "OPEN":
                    continue
                player = _player_from_market_name(
                    str(market.get("name") or ""), participant.get("mediumName")
                )
                if not player:
                    continue

                over = under = None
                line: float | None = None
                for selection in market.get("selections") or []:
                    side = str(selection.get("type") or "").upper()
                    sel_open = str(selection.get("status") or "").upper() == "OPEN"
                    if side == "OVER":
                        if sel_open:
                            over = _parse_odds(selection)
                        line = _selection_line(selection) if line is None else line
                    elif side == "UNDER":
                        if sel_open:
                            under = _parse_odds(selection)
                        line = _selection_line(selection) if line is None else line
                if over is None or under is None or line is None:
                    continue

                key = (player, canonical_market)
                prop = grouped.get(key)
                if prop is None:
                    prop = {
                        "sportsbook": ESPN_SPORTSBOOK,
                        "event_id": event_id,
                        "tab": section_slug,
                        "player": player,
                        "market": canonical_market,
                        "line_kind": LINE_KIND_OU,
                        "lines": [],
                    }
                    grouped[key] = prop
                prop["lines"].append(
                    {
                        "line": line,
                        "over_odds": over,
                        "under_odds": under,
                        "is_main_line": True,
                        "market_id": market.get("id"),
                        "market_type": market.get("type"),
                    }
                )

    for prop in grouped.values():
        prop["lines"].sort(key=lambda entry: entry["line"])
    return list(grouped.values())


def count_espn_line_rows(props: list[dict[str, Any]]) -> int:
    """Count O/U line rows across grouped (or legacy flat) master-board props."""
    total = 0
    for prop in props:
        lines = prop.get("lines")
        if lines:
            total += len(lines)
        elif prop.get("line") is not None:
            total += 1
    return total


def _parse_milestone_clean_name(selection: dict[str, Any]) -> int | None:
    """Parse threshold N from ``selection.name.cleanName`` == ``"N+"``; else None."""
    clean = ((selection.get("name") or {}).get("cleanName") or "")
    if not clean.endswith("+"):
        return None
    try:
        return int(clean[:-1])
    except ValueError:
        return None


def flatten_milestone_drawer_content(
    payload: dict[str, Any],
    *,
    event_id: str,
    league: str,
    label_text: str,
    section_slug: str | None = None,
) -> list[dict[str, Any]]:
    """Flatten an EventDrawerContent LIST (milestone) leaf into flat prop rows.

    Handles two card formats in ``drawerChildren[].marketplaceShelfChildren[]``:

    *  ``markets[]`` — ``market.type == "LIST"``, full player name from
       ``market.name`` via ``" Total "`` split, ``market.status`` checked.
    *  ``rows[]`` — ``__typename == "TableMarketCardRow"``, abbreviated player
       name from ``row.label``; null entries in ``selections`` are skipped.

    ``"N+"`` ``selection.name.cleanName`` → line = ``N − 0.5``.  Only ``"OPEN"``
    selections with non-null odds are emitted.  Returns one flat dict per
    ``(player, line)`` with ``line_kind = "milestone"``.
    """
    _ = league
    canonical_market = canonical_market_for_milestone_label(label_text)
    if not canonical_market:
        return []

    drawer = (payload.get("data") or {}).get("eventDrawer") or {}
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, float]] = set()

    for shelf in drawer.get("drawerChildren") or []:
        for card in shelf.get("marketplaceShelfChildren") or []:

            # --- Format 1: markets[] (full player name, LIST type) ---
            for market in card.get("markets") or []:
                if str(market.get("type") or "").upper() != "LIST":
                    continue
                if str(market.get("status") or "").upper() != "OPEN":
                    continue
                player = _player_from_market_name(str(market.get("name") or ""), None)
                if not player:
                    continue
                for selection in market.get("selections") or []:
                    if selection is None:
                        continue
                    if str(selection.get("status") or "").upper() != "OPEN":
                        continue
                    threshold = _parse_milestone_clean_name(selection)
                    if threshold is None:
                        continue
                    odds = _parse_odds(selection)
                    if odds is None:
                        continue
                    line = float(threshold) - 0.5
                    key = (player, line)
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append(
                        {
                            "sportsbook": ESPN_SPORTSBOOK,
                            "event_id": event_id,
                            "tab": section_slug,
                            "player": player,
                            "market": canonical_market,
                            "line": line,
                            "line_kind": LINE_KIND_MILESTONE,
                            "milestone_threshold": threshold,
                            "over_odds": odds,
                            "under_odds": None,
                            "is_main_line": threshold == 1,
                            "market_id": selection.get("id"),
                        }
                    )

            # --- Format 2: rows[] (abbreviated player name, no market-level status) ---
            for row in card.get("rows") or []:
                if row is None:
                    continue
                if row.get("__typename") != "TableMarketCardRow":
                    continue
                player = (row.get("label") or "").strip()
                if not player:
                    continue
                for selection in (row.get("selections") or []):
                    if selection is None:
                        continue
                    if str(selection.get("status") or "").upper() != "OPEN":
                        continue
                    threshold = _parse_milestone_clean_name(selection)
                    if threshold is None:
                        continue
                    odds = _parse_odds(selection)
                    if odds is None:
                        continue
                    line = float(threshold) - 0.5
                    key = (player, line)
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append(
                        {
                            "sportsbook": ESPN_SPORTSBOOK,
                            "event_id": event_id,
                            "tab": section_slug,
                            "player": player,
                            "market": canonical_market,
                            "line": line,
                            "line_kind": LINE_KIND_MILESTONE,
                            "milestone_threshold": threshold,
                            "over_odds": odds,
                            "under_odds": None,
                            "is_main_line": threshold == 1,
                            "market_id": selection.get("id"),
                        }
                    )

    return rows
