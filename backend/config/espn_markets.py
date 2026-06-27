"""ESPN (TheScore Bet) per-event drawer → canonical market dispatch.

Player props live in per-event ``Section`` drawers (``pitcher-props`` / ``batter-props``).
Each stat has two drawers: a milestone/LIST drawer (UUID ``groupId``, labelText e.g.
``"Singles"``) and an over/under drawer whose ``groupId`` is the literal ``"<Stat>(O/U)"``.
O/U drawers use ``selection.type`` OVER/UNDER with the line in ``selection.points.decimalPoints``.
Milestone (LIST) drawers use ``selection.name.cleanName`` of ``"N+"`` → line = N − 0.5.
Canonical names come from ``config/market_maps.py``.
"""

from __future__ import annotations

# Per-event section slugs that carry player-prop drawers, per league.
ESPN_PROP_SECTION_SLUGS_BY_LEAGUE: dict[str, tuple[str, ...]] = {
    "mlb": ("pitcher-props", "batter-props"),
    # WNBA TBD until its own capture (decision 8).
    "wnba": (),
}

# Literal O/U drawer groupId -> canonical market key (identity-mapped in market_maps).
# UUID groupIds are the N+/LIST milestone drawers; those are dispatched via labelText.
ESPN_OU_GROUP_TO_MARKET: dict[str, str] = {
    "PitcherStrikeouts(O/U)": "strikeouts",
    "OutsRecorded(O/U)": "total_outs",
    "HitsAllowed(O/U)": "hits_allowed",
    "WalksAllowed(O/U)": "pitching_walks",
    "Hits(O/U)": "hits",
    "TotalBases(O/U)": "total_bases",
    "RBIs(O/U)": "rbi",
    "HomeRuns(O/U)": "home_runs",
    "Hits+Runs+RBIs(O/U)": "h+r+rbi",
}

ESPN_MLB_PITCHER_OU_MARKETS: tuple[str, ...] = (
    "strikeouts",
    "total_outs",
    "hits_allowed",
    "pitching_walks",
)
ESPN_MLB_BATTER_OU_MARKETS: tuple[str, ...] = (
    "hits",
    "total_bases",
    "rbi",
    "home_runs",
    "h+r+rbi",
)
# Milestone-only MLB batter markets (no O/U drawer exists on ESPN).
ESPN_MLB_BATTER_MILESTONE_MARKETS: tuple[str, ...] = (
    "singles",
    "doubles",
    "runs",
    "stolen_bases",
)

# Milestone drawer labelText -> canonical market key.
ESPN_MILESTONE_LABEL_TO_MARKET: dict[str, str] = {
    "Singles": "singles",
    "Doubles": "doubles",
    "Runs": "runs",
    "Stolen Bases": "stolen_bases",
}

ESPN_MLB_DEFAULT_SCRAPE_MARKETS: tuple[str, ...] = (
    *ESPN_MLB_PITCHER_OU_MARKETS,
    *ESPN_MLB_BATTER_OU_MARKETS,
    *ESPN_MLB_BATTER_MILESTONE_MARKETS,
)

ESPN_DEFAULT_SCRAPE_MARKETS_BY_LEAGUE: dict[str, tuple[str, ...]] = {
    "mlb": ESPN_MLB_DEFAULT_SCRAPE_MARKETS,
    "wnba": (),
}


def _league_key(league: str) -> str:
    return league.lower()


def prop_section_slugs_for_league(league: str) -> tuple[str, ...]:
    """Return the per-event section slugs that hold O/U drawers for a league."""
    return ESPN_PROP_SECTION_SLUGS_BY_LEAGUE[_league_key(league)]


def default_scrape_markets_for_league(league: str) -> tuple[str, ...]:
    """Return the default canonical O/U markets to scrape for a league."""
    return ESPN_DEFAULT_SCRAPE_MARKETS_BY_LEAGUE[_league_key(league)]


def known_markets_for_league(league: str) -> frozenset[str]:
    """All canonical O/U markets ESPN can return for a league."""
    return frozenset(default_scrape_markets_for_league(league))


def is_ou_group_id(group_id: str | None) -> bool:
    """True for a literal over/under drawer groupId (``"<Stat>(O/U)"``)."""
    return bool(group_id) and group_id in ESPN_OU_GROUP_TO_MARKET


def canonical_market_for_group_id(group_id: str | None) -> str | None:
    """Map a literal O/U drawer groupId to a canonical market, else None.

    Returns None for milestone/LIST drawers (UUID groupIds) and unknown stats.
    """
    if not group_id:
        return None
    return ESPN_OU_GROUP_TO_MARKET.get(group_id)


def is_milestone_label(label_text: str | None) -> bool:
    """True for a milestone drawer labelText in ``ESPN_MILESTONE_LABEL_TO_MARKET``."""
    return bool(label_text) and label_text in ESPN_MILESTONE_LABEL_TO_MARKET


def canonical_market_for_milestone_label(label_text: str | None) -> str | None:
    """Map a milestone drawer labelText to a canonical market, else None."""
    if not label_text:
        return None
    return ESPN_MILESTONE_LABEL_TO_MARKET.get(label_text)
