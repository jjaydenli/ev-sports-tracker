"""FanDuel sportsbook API client (league slate / event discovery / flatten)."""

from __future__ import annotations

import re
from typing import Any

import httpx
from loguru import logger

from config.api_headers import FD_BASE_HEADERS
from config.fd_competitions import (
    FD_LEAGUE_SLATES,
    build_content_managed_page_url,
    build_event_page_url,
    extract_event_ids,
)
from config.fd_markets import (
    FD_SGP_TAB,
    canonical_market_for_tab,
    is_multi_market_tab,
    is_player_ou_market_for_tab,
    parse_player_ou_market_type,
)
from utils.formatting import normalize_odds_string

FD_SPORTSBOOK = "FanDuel"
LINE_KIND_OU = "ou"

RUNNER_SIDE_LINE_RE = re.compile(
    r"^(?P<player>.+?)\s+(?P<side>Over|Under)(?:\s+(?P<line>\d+(?:\.\d+)?))?$",
    re.IGNORECASE,
)


async def fetch_league_events(
    client: httpx.AsyncClient,
    league: str = "nba",
) -> dict[str, Any] | None:
    """Fetch the FanDuel custom league page payload (attachments.events)."""
    if league not in FD_LEAGUE_SLATES:
        logger.error(f"unknown fanduel league: {league}")
        return None

    url = build_content_managed_page_url(league)
    try:
        response = await client.get(url, headers=FD_BASE_HEADERS, timeout=15.0)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:500]
        logger.error(
            f"fanduel league api blocked request: {exc.response.status_code} — {body}"
        )
        return None
    except httpx.RequestError as exc:
        logger.error(f"fanduel league api request failed: {exc}")
        return None


async def fetch_league_event_ids(
    client: httpx.AsyncClient,
    league: str = "nba",
    *,
    require_matchup: bool = True,
) -> list[str]:
    """Fetch NBA (or other league) matchup event IDs from the league custom page."""
    payload = await fetch_league_events(client, league)
    if not payload:
        return []

    slate = FD_LEAGUE_SLATES[league]
    return extract_event_ids(
        payload,
        competition_id=slate["competition_id"],
        require_matchup=require_matchup,
    )


async def fetch_event_page(
    client: httpx.AsyncClient,
    event_id: str,
    *,
    tab: str = "player-points",
) -> dict[str, Any] | None:
    """Fetch FanDuel per-event markets for one tab (increment 2)."""
    url = build_event_page_url(event_id, tab=tab)
    try:
        response = await client.get(url, headers=FD_BASE_HEADERS, timeout=15.0)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:500]
        logger.error(
            f"fanduel event-page blocked request: {exc.response.status_code} — {body}"
        )
        return None
    except httpx.RequestError as exc:
        logger.error(f"fanduel event-page request failed: {exc}")
        return None


def parse_fd_american_odds(runner: dict[str, Any]) -> int | None:
    """Parse FanDuel winRunnerOdds into an integer American line."""
    odds_block = runner.get("winRunnerOdds") or {}
    american = odds_block.get("americanDisplayOdds") or {}
    raw = american.get("americanOddsInt")
    if raw is None:
        raw = american.get("americanOdds")
    if raw is None:
        return None
    try:
        return int(normalize_odds_string(str(raw)))
    except ValueError:
        return None


def _player_from_market_name(market_name: str) -> str | None:
    if " - " not in market_name:
        return None
    return market_name.split(" - ", 1)[0].strip() or None


def _parse_runner_side_line(runner_name: str) -> tuple[str, str, float | None]:
    match = RUNNER_SIDE_LINE_RE.match(runner_name.strip())
    if not match:
        raise ValueError(f"unrecognized runner name: {runner_name!r}")
    player = match.group("player").strip()
    side = match.group("side").lower()
    line_raw = match.group("line")
    line = float(line_raw) if line_raw is not None else None
    return player, side, line


def _group_main_line_runners(
    runners: list[dict[str, Any]],
    *,
    player: str,
) -> dict[float, dict[str, Any]]:
    grouped: dict[float, dict[str, Any]] = {}
    for runner in runners:
        result_type = str((runner.get("result") or {}).get("type") or "").upper()
        side = result_type.lower() if result_type in {"OVER", "UNDER"} else None
        if side is None:
            _, side, _ = _parse_runner_side_line(str(runner.get("runnerName") or ""))
        handicap = runner.get("handicap")
        if handicap is None:
            continue
        line = float(handicap)
        entry = grouped.setdefault(line, {})
        entry[side] = runner
    return grouped


def _group_alt_line_runners(
    runners: list[dict[str, Any]],
) -> dict[tuple[str, float], dict[str, Any]]:
    grouped: dict[tuple[str, float], dict[str, Any]] = {}
    for runner in runners:
        try:
            player, side, line = _parse_runner_side_line(str(runner.get("runnerName") or ""))
        except ValueError:
            continue
        if line is None:
            continue
        entry = grouped.setdefault((player, line), {})
        entry[side] = runner
    return grouped


def _append_ou_row(
    props: list[dict[str, Any]],
    seen: set[tuple[str, str, float]],
    *,
    event_id: str,
    tab: str,
    market_id: str,
    market_type: str,
    player: str,
    canonical_market: str,
    line: float,
    over_runner: dict[str, Any],
    under_runner: dict[str, Any],
    is_main_line: bool,
) -> None:
    over_odds = parse_fd_american_odds(over_runner)
    under_odds = parse_fd_american_odds(under_runner)
    if over_odds is None or under_odds is None:
        return

    dedupe_key = (player, canonical_market, line)
    if dedupe_key in seen:
        return
    seen.add(dedupe_key)

    props.append(
        {
            "sportsbook": FD_SPORTSBOOK,
            "event_id": event_id,
            "tab": tab,
            "market_id": market_id,
            "market_type": market_type,
            "player": player,
            "market": canonical_market,
            "line": line,
            "line_kind": LINE_KIND_OU,
            "over_odds": over_odds,
            "under_odds": under_odds,
            "is_main_line": is_main_line,
        }
    )


def flatten_player_ou_market(
    fd_market: dict[str, Any],
    *,
    event_id: str,
    tab: str,
    canonical_market: str,
    league: str = "nba",
) -> list[dict[str, Any]]:
    """Flatten one FanDuel main or alt player O/U market into master-board rows."""
    market_type = str(fd_market.get("marketType") or "")
    parsed = parse_player_ou_market_type(market_type, league=league)
    if not parsed:
        return []

    parsed_market, is_alt = parsed
    if parsed_market != canonical_market:
        return []

    market_id = str(fd_market.get("marketId") or "")
    market_name = str(fd_market.get("marketName") or "")
    runners = fd_market.get("runners") or []
    props: list[dict[str, Any]] = []
    seen: set[tuple[str, str, float]] = set()

    if is_alt:
        for (player, line), sides in _group_alt_line_runners(runners).items():
            over_runner = sides.get("over")
            under_runner = sides.get("under")
            if not over_runner or not under_runner:
                continue
            _append_ou_row(
                props,
                seen,
                event_id=event_id,
                tab=tab,
                market_id=market_id,
                market_type=market_type,
                player=player,
                canonical_market=canonical_market,
                line=line,
                over_runner=over_runner,
                under_runner=under_runner,
                is_main_line=False,
            )
        return props

    player = _player_from_market_name(market_name)
    if not player:
        return []

    for line, sides in _group_main_line_runners(runners, player=player).items():
        over_runner = sides.get("over")
        under_runner = sides.get("under")
        if not over_runner or not under_runner:
            continue
        _append_ou_row(
            props,
            seen,
            event_id=event_id,
            tab=tab,
            market_id=market_id,
            market_type=market_type,
            player=player,
            canonical_market=canonical_market,
            line=line,
            over_runner=over_runner,
            under_runner=under_runner,
            is_main_line=True,
        )
    return props


def merge_prop_rows(props: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Dedupe rows by player/market/line; prefer is_main_line when main and alt overlap."""
    merged: dict[tuple[str, str, float], dict[str, Any]] = {}
    for prop in props:
        key = (prop["player"], prop["market"], float(prop["line"]))
        existing = merged.get(key)
        if existing is None or (
            prop.get("is_main_line") and not existing.get("is_main_line")
        ):
            merged[key] = prop
    return list(merged.values())


def group_fd_line_rows(line_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Group flattened O/U line rows into one master-board prop per player + market.

    Each prop carries a ``lines`` ladder (main + alts). Downstream normalization
    expands these back to line-level rows for ``build_player_market_ladder``.
    """
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}

    for row in line_rows:
        key = (str(row["event_id"]), row["player"], row["market"])
        prop = grouped.get(key)
        if prop is None:
            prop = {
                "sportsbook": row.get("sportsbook", FD_SPORTSBOOK),
                "event_id": row["event_id"],
                "tab": row.get("tab"),
                "player": row["player"],
                "market": row["market"],
                "line_kind": row.get("line_kind", LINE_KIND_OU),
                "lines": [],
            }
            grouped[key] = prop

        prop["lines"].append(
            {
                "line": float(row["line"]),
                "over_odds": row["over_odds"],
                "under_odds": row["under_odds"],
                "is_main_line": bool(row.get("is_main_line", False)),
                "market_id": row.get("market_id"),
                "market_type": row.get("market_type"),
            }
        )

    for prop in grouped.values():
        prop["lines"].sort(
            key=lambda entry: (not entry["is_main_line"], entry["line"])
        )

    return list(grouped.values())


def count_fd_line_rows(props: list[dict[str, Any]]) -> int:
    """Count O/U line rows across grouped or legacy flat master-board props."""
    total = 0
    for prop in props:
        lines = prop.get("lines")
        if lines:
            total += len(lines)
        elif prop.get("line") is not None:
            total += 1
    return total


def event_page_in_play(payload: dict[str, Any], event_id: str) -> bool:
    attachments = payload.get("attachments") or {}
    events = attachments.get("events") or {}
    event = events.get(str(event_id)) or events.get(int(event_id)) or {}
    return bool(event.get("inPlay"))


def flatten_event_page_response(
    payload: dict[str, Any],
    *,
    event_id: str,
    tab: str,
    markets: set[str] | None = None,
    league: str = "nba",
) -> list[dict[str, Any]]:
    """
    Flatten FanDuel event-page attachments.markets into grouped O/U master-board props.

    Uses main (PLAYER_*_TOTAL_* / PITCHER_*_TOTAL_*) and alt ladders only.
    Skips milestones (TO_SCORE_*), game lines, and quarter props.
    """
    if event_page_in_play(payload, event_id):
        logger.info(f"skip in-play fanduel event {event_id}")
        return []

    attachments = payload.get("attachments") or {}
    fd_markets = attachments.get("markets") or {}
    line_rows: list[dict[str, Any]] = []

    if tab == FD_SGP_TAB or is_multi_market_tab(tab, league=league):
        allowed = markets
        for fd_market in fd_markets.values():
            market_type = str(fd_market.get("marketType") or "")
            parsed = parse_player_ou_market_type(market_type, league=league)
            if not parsed:
                continue
            canonical_market, _ = parsed
            if allowed is not None and canonical_market not in allowed:
                continue
            line_rows.extend(
                flatten_player_ou_market(
                    fd_market,
                    event_id=event_id,
                    tab=tab,
                    canonical_market=canonical_market,
                    league=league,
                )
            )
    else:
        canonical_market = canonical_market_for_tab(tab, league=league)
        if not canonical_market:
            logger.error(f"unknown fanduel tab for flatten: {tab}")
            return []
        if markets is not None and canonical_market not in markets:
            return []

        for fd_market in fd_markets.values():
            market_type = str(fd_market.get("marketType") or "")
            if not is_player_ou_market_for_tab(market_type, tab, league=league):
                continue
            line_rows.extend(
                flatten_player_ou_market(
                    fd_market,
                    event_id=event_id,
                    tab=tab,
                    canonical_market=canonical_market,
                    league=league,
                )
            )

    return group_fd_line_rows(merge_prop_rows(line_rows))


async def fetch_and_flatten_event_page(
    client: httpx.AsyncClient,
    event_id: str,
    *,
    tab: str,
    markets: set[str] | None = None,
    league: str = "nba",
) -> list[dict[str, Any]]:
    """Fetch one event-page tab and return grouped O/U master-board props."""
    payload = await fetch_event_page(client, event_id, tab=tab)
    if not payload:
        return []
    return flatten_event_page_response(
        payload,
        event_id=event_id,
        tab=tab,
        markets=markets,
        league=league,
    )
