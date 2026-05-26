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

# Default scrape targets: player-prop tabs with main + alt O/U ladders (not SGP / milestones).
FD_PLAYER_PROP_TABS: tuple[str, ...] = tuple(FD_TAB_CANONICAL_MARKETS)

_STAT_SUFFIX_TO_CANONICAL = {
    "POINTS": "points",
    "REBOUNDS": "rebounds",
    "ASSISTS": "assists",
}

# PLAYER_A_TOTAL_POINTS / PLAYER_A_ALT_TOTAL_REBOUNDS etc.
FD_PLAYER_OU_MARKET_RE = re.compile(
    r"^PLAYER_[A-Z]_(?P<alt>ALT_)?TOTAL_(?P<stat>POINTS|REBOUNDS|ASSISTS)$"
)


def canonical_market_for_tab(tab: str) -> str | None:
    return FD_TAB_CANONICAL_MARKETS.get(tab)


def tab_for_canonical_market(market: str) -> str | None:
    return FD_CANONICAL_TO_TAB.get(market)


def parse_player_ou_market_type(market_type: str) -> tuple[str, bool] | None:
    """
    Return (canonical_market, is_alt) for a FanDuel player O/U marketType.

    Returns None for milestones, game lines, quarter props, and other non-O/U boards.
    """
    match = FD_PLAYER_OU_MARKET_RE.match(market_type or "")
    if not match:
        return None
    stat = _STAT_SUFFIX_TO_CANONICAL.get(match.group("stat"))
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
