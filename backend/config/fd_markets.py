"""FanDuel event-page tab and player O/U market type mapping."""

from __future__ import annotations

import re

# event-page ?tab= slug → canonical market key (matches market_maps / Betr).
FD_TAB_CANONICAL_MARKETS: dict[str, str] = {
    "player-points": "points",
    "player-rebounds": "rebounds",
    "player-assists": "assists",
}

FD_CANONICAL_TO_TAB: dict[str, str] = {
    market: tab for tab, market in FD_TAB_CANONICAL_MARKETS.items()
}

FD_SGP_TAB = "same-game-parlay-"

# Player-prop tabs with main + alt O/U ladders (not SGP / milestones).
FD_PLAYER_PROP_TABS: tuple[str, ...] = tuple(FD_TAB_CANONICAL_MARKETS)

# Extended O/U stats available on the SGP tab (not dedicated tabs).
FD_EXTENDED_OU_MARKETS: tuple[str, ...] = (
    "threes",
    "pts+reb",
    "pts+ast",
    "pra",
    "reb+ast",
)

# Default scrape: core tabs + SGP extended O/U (matches Betr/DK coverage where FD offers lines).
FD_DEFAULT_SCRAPE_MARKETS: tuple[str, ...] = (
    *FD_TAB_CANONICAL_MARKETS.values(),
    *FD_EXTENDED_OU_MARKETS,
)

# Longest suffix first so combo stats match before single-stat keys.
_STAT_SUFFIX_TO_CANONICAL: tuple[tuple[str, str], ...] = (
    ("POINTS_+_REB_+_AST", "pra"),
    ("PTS_+_REB_+_AST", "pra"),
    ("POINTS_+_REBOUNDS", "pts+reb"),
    ("PTS_+_REB", "pts+reb"),
    ("POINTS_+_ASSISTS", "pts+ast"),
    ("PTS_+_AST", "pts+ast"),
    ("REBOUNDS_+_ASSISTS", "reb+ast"),
    ("REB_+_AST", "reb+ast"),
    ("MADE_3_POINT_FIELD_GOALS", "threes"),
    ("THREES", "threes"),
    ("POINTS", "points"),
    ("REBOUNDS", "rebounds"),
    ("ASSISTS", "assists"),
)

# PLAYER_A_TOTAL_POINTS / PLAYER_A_ALT_TOTAL_PTS_+_REB_+_AST etc.
FD_PLAYER_OU_MARKET_RE = re.compile(
    r"^PLAYER_[A-Z]_(?P<alt>ALT_)?TOTAL_(?P<stat>.+)$"
)


def canonical_market_for_tab(tab: str) -> str | None:
    return FD_TAB_CANONICAL_MARKETS.get(tab)


def tab_for_canonical_market(market: str) -> str | None:
    return FD_CANONICAL_TO_TAB.get(market)


def _canonical_for_stat_suffix(stat_suffix: str) -> str | None:
    for suffix, market in _STAT_SUFFIX_TO_CANONICAL:
        if stat_suffix == suffix:
            return market
    return None


def parse_player_ou_market_type(market_type: str) -> tuple[str, bool] | None:
    """
    Return (canonical_market, is_alt) for a FanDuel player O/U marketType.

    Returns None for milestones, game lines, quarter props, and other non-O/U boards.
    """
    match = FD_PLAYER_OU_MARKET_RE.match(market_type or "")
    if not match:
        return None
    stat = _canonical_for_stat_suffix(match.group("stat"))
    if not stat:
        return None
    return stat, bool(match.group("alt"))


def is_player_ou_market_for_tab(market_type: str, tab: str) -> bool:
    """True when marketType is a main or alt player O/U ladder for this tab's stat."""
    parsed = parse_player_ou_market_type(market_type)
    if not parsed:
        return False
    market, _ = parsed
    return market == canonical_market_for_tab(tab)


def is_extended_ou_market(market: str) -> bool:
    return market in FD_EXTENDED_OU_MARKETS


def is_core_ou_market(market: str) -> bool:
    return market in FD_CANONICAL_TO_TAB
