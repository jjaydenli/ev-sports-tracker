"""Build ladder lookup structures from raw prop lists."""

from __future__ import annotations

from typing import Any

from loguru import logger

def _hour_floor(iso: str) -> str:
    """Hour-precision prefix of an ISO UTC timestamp (e.g. 2026-06-19T17)."""
    return iso[:13] if iso else ""


def build_match_context_key(
    prop: dict,
    *,
    normalize_player_name,
) -> str:
    """
    Canonical match-context key: player|market|league|[event_hour]|[live].

    Line-agnostic; ``event_hour`` is UTC hour-floor (``iso[:13]``) when
    ``event_start`` is present and is the sole game discriminator. Live rows
    omit the hour (books disagree on in-game timestamps); pregame rows without
    ``event_start`` omit the hour as well.
    """
    key = f"{normalize_player_name(prop['player'])}|{prop['market']}"
    league = prop.get("league")
    if league:
        key = f"{key}|{str(league).upper()}"
    event_start = prop.get("event_start", "")
    is_live = bool(prop.get("is_live"))
    if event_start and not is_live:
        key = f"{key}|{_hour_floor(event_start)}"
    if is_live:
        key = f"{key}|live"
    return key


def _event_start_from_row(row: dict[str, Any]) -> str | None:
    start = row.get("event_start") or ""
    return start if start else None


def build_player_market_key(
    prop: dict,
    *,
    normalize_player_name,
) -> str:
    """
    Player + market ladder key, optionally scoped by event-hour and live snapshot.

    Live Betr rows carry ``is_live``; sharp books tag live DK rows the same way.
    ``event_hour`` is the UTC hour-floor (``iso[:13]``) of ``event_start`` and is the
    sole game discriminator, so back-to-back matchups (same teams, different start
    times) do not collide. Pregame rows omit the live suffix.
    """
    key = f"{normalize_player_name(prop['player'])}|{prop['market']}"
    event_start = prop.get("event_start", "")
    is_live = bool(prop.get("is_live"))
    if event_start and not is_live:
        key = f"{key}|{_hour_floor(event_start)}"
    if is_live:
        key = f"{key}|live"
    return key


def _collision_is_ambiguous(
    existing: dict[str, Any], new_over: int, new_under: int | None
) -> bool:
    """True when a same-line ladder collision carries *conflicting* odds.

    Identical odds are a harmless duplicate (same EV either way) and may overwrite
    silently. Differing odds at the same ``player|market|hour|line`` are
    unresolvable — most often two distinct players colliding under one normalized
    name — so the key is dropped from matching rather than silently resolved to
    whichever row wrote last. See the ``team``/player-id disambiguation notes; the
    match gate has no player identity beyond the normalized name today.
    """
    if existing["over_odds"] != new_over:
        return True
    return existing.get("under_odds") != new_under


def build_player_market_ladder(
    dk_props: list[dict],
    *,
    normalize_player_name,
) -> dict[str, dict[float, dict[str, Any]]]:
    """Index DK O/U rows by player|market -> line -> odds metadata.

    A same-line collision with conflicting odds marks the whole ``pm_key``
    ambiguous and drops it, so an unresolvable same-name clash yields no match
    rather than a silent wrong-odds match.
    """
    ladder: dict[str, dict[float, dict[str, Any]]] = {}
    ambiguous: set[str] = set()
    for prop in dk_props:
        if prop.get("line_kind", "ou") == "milestone":
            continue
        over_odds = prop.get("over_odds")
        under_odds = prop.get("under_odds")
        if over_odds is None or under_odds is None:
            continue
        pm_key = build_player_market_key(prop, normalize_player_name=normalize_player_name)
        line = float(prop["line"])
        bucket = ladder.setdefault(pm_key, {})
        existing = bucket.get(line)
        if existing is not None and _collision_is_ambiguous(
            existing, int(over_odds), int(under_odds)
        ):
            logger.warning(
                "ambiguous sharp O/U collision — dropping pm_key={pm_key} from "
                "matching line={line} event_start={event_start}",
                pm_key=pm_key,
                line=line,
                event_start=prop.get("event_start", ""),
            )
            ambiguous.add(pm_key)
        bucket[line] = {
            "over_odds": int(over_odds),
            "under_odds": int(under_odds),
            "is_main_line": bool(prop.get("is_main_line", True)),
            "event_start": prop.get("event_start", ""),
        }
    for pm_key in ambiguous:
        ladder.pop(pm_key, None)
    return ladder


def build_milestone_ladder(
    sharp_props: list[dict],
    *,
    normalize_player_name,
) -> dict[str, dict[float, dict[str, Any]]]:
    """Index milestone (N+) rows by player|market -> converted line -> over odds.

    A same-line collision with conflicting over odds drops the ``pm_key`` from
    matching, matching ``build_player_market_ladder``'s ambiguity handling.
    """
    ladder: dict[str, dict[float, dict[str, Any]]] = {}
    ambiguous: set[str] = set()
    for prop in sharp_props:
        if prop.get("line_kind") != "milestone":
            continue
        over_odds = prop.get("over_odds")
        if over_odds is None:
            continue
        pm_key = build_player_market_key(prop, normalize_player_name=normalize_player_name)
        line = float(prop["line"])
        source_book = prop.get("sportsbook", "DraftKings")
        bucket = ladder.setdefault(pm_key, {})
        existing = bucket.get(line)
        if existing is not None and _collision_is_ambiguous(
            existing, int(over_odds), None
        ):
            logger.warning(
                "ambiguous sharp milestone collision — dropping pm_key={pm_key} "
                "from matching line={line} event_start={event_start}",
                pm_key=pm_key,
                line=line,
                event_start=prop.get("event_start", ""),
            )
            ambiguous.add(pm_key)
        bucket[line] = {
            "over_odds": int(over_odds),
            "milestone_threshold": prop.get("milestone_threshold"),
            "is_main_line": bool(prop.get("is_main_line", True)),
            "sportsbook": source_book,
            "event_start": prop.get("event_start", ""),
        }
    for pm_key in ambiguous:
        ladder.pop(pm_key, None)
    return ladder


def build_milestone_ladders(
    sharp_props: list[dict],
    *,
    normalize_player_name,
) -> dict[str, dict[str, dict[float, dict[str, Any]]]]:
    """Per-book milestone ladders keyed by sportsbook name.

    A same-line collision with conflicting over odds drops the ``(book, pm_key)``
    from matching, matching ``build_player_market_ladder``'s ambiguity handling.
    """
    ladders: dict[str, dict[str, dict[float, dict[str, Any]]]] = {}
    ambiguous: set[tuple[str, str]] = set()
    for prop in sharp_props:
        if prop.get("line_kind") != "milestone":
            continue
        over_odds = prop.get("over_odds")
        if over_odds is None:
            continue
        source_book = prop.get("sportsbook", "DraftKings")
        pm_key = build_player_market_key(prop, normalize_player_name=normalize_player_name)
        line = float(prop["line"])
        bucket = ladders.setdefault(source_book, {}).setdefault(pm_key, {})
        existing = bucket.get(line)
        if existing is not None and _collision_is_ambiguous(
            existing, int(over_odds), None
        ):
            logger.warning(
                "ambiguous sharp per-book milestone collision — dropping "
                "book={book} pm_key={pm_key} from matching line={line} "
                "event_start={event_start}",
                book=source_book,
                pm_key=pm_key,
                line=line,
                event_start=prop.get("event_start", ""),
            )
            ambiguous.add((source_book, pm_key))
        bucket[line] = {
            "over_odds": int(over_odds),
            "milestone_threshold": prop.get("milestone_threshold"),
            "is_main_line": bool(prop.get("is_main_line", True)),
            "sportsbook": source_book,
            "event_start": prop.get("event_start", ""),
        }
    for source_book, pm_key in ambiguous:
        ladders.get(source_book, {}).pop(pm_key, None)
    return ladders


def merge_milestone_ladders(
    ladders: dict[str, dict[str, dict[float, dict[str, Any]]]],
    *,
    book_precedence: tuple[str, ...] = ("DraftKings", "FanDuel"),
) -> dict[str, dict[float, dict[str, Any]]]:
    """Merge per-book milestone ladders; earlier books win on line collisions."""
    merged: dict[str, dict[float, dict[str, Any]]] = {}
    for book in book_precedence:
        for pm_key, lines in ladders.get(book, {}).items():
            merged.setdefault(pm_key, {})
            for line, row in lines.items():
                if line not in merged[pm_key]:
                    merged[pm_key][line] = row
    return merged
