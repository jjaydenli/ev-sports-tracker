"""FanDuel event-page tab and player O/U market type mapping."""

from __future__ import annotations

import re

# --- NBA (legacy module-level aliases; behavior unchanged) ---

FD_TAB_CANONICAL_MARKETS: dict[str, str] = {
    "player-points": "points",
    "player-rebounds": "rebounds",
    "player-assists": "assists",
}

FD_CANONICAL_TO_TAB: dict[str, str] = {
    market: tab for tab, market in FD_TAB_CANONICAL_MARKETS.items()
}

FD_SGP_TAB = "same-game-parlay-"

FD_PLAYER_PROP_TABS: tuple[str, ...] = tuple(FD_TAB_CANONICAL_MARKETS)

FD_EXTENDED_OU_MARKETS: tuple[str, ...] = (
    "threes",
    "pts+reb",
    "pts+ast",
    "pra",
    "reb+ast",
)

FD_DEFAULT_SCRAPE_MARKETS: tuple[str, ...] = (
    *FD_TAB_CANONICAL_MARKETS.values(),
    *FD_EXTENDED_OU_MARKETS,
)

_STAT_SUFFIX_TO_CANONICAL_NBA: tuple[tuple[str, str], ...] = (
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

# --- MLB ---

FD_MLB_PITCHER_TAB = "pitcher-props"
FD_MLB_BATTER_TAB = "batter-props"

FD_MLB_PITCHER_OU_MARKETS: tuple[str, ...] = (
    "strikeouts",
    "earned_runs",
    "total_outs",
    "pitching_walks",
    "hits_allowed",
)

FD_MLB_BATTER_OU_MARKETS: tuple[str, ...] = (
    "hits",
    "total_bases",
    "runs",
    "rbi",
    "h+r+rbi",
    "singles",
    "doubles",
    "walks",
)

FD_MLB_DEFAULT_SCRAPE_MARKETS: tuple[str, ...] = (
    *FD_MLB_PITCHER_OU_MARKETS,
    *FD_MLB_BATTER_OU_MARKETS,
)

FD_MLB_TAB_MARKETS: dict[str, tuple[str, ...]] = {
    FD_MLB_PITCHER_TAB: FD_MLB_PITCHER_OU_MARKETS,
    FD_MLB_BATTER_TAB: FD_MLB_BATTER_OU_MARKETS,
}

_STAT_SUFFIX_TO_CANONICAL_MLB: tuple[tuple[str, str], ...] = (
    ("HITS_+_RUNS_+_RBIS", "h+r+rbi"),
    ("HITS_+_RUNS_+_RBI", "h+r+rbi"),
    ("TOTAL_BASES", "total_bases"),
    ("STRIKEOUTS", "strikeouts"),
    ("EARNED_RUNS", "earned_runs"),
    ("PITCHING_WALKS", "pitching_walks"),
    ("HITS_ALLOWED", "hits_allowed"),
    ("TOTAL_OUTS", "total_outs"),
    ("SINGLES", "singles"),
    ("DOUBLES", "doubles"),
    ("WALKS", "walks"),
    ("HITS", "hits"),
    ("RUNS", "runs"),
    ("RBIS", "rbi"),
    ("RBI", "rbi"),
)

# --- Per-league registries ---

FD_TAB_CANONICAL_MARKETS_BY_LEAGUE: dict[str, dict[str, str]] = {
    "nba": dict(FD_TAB_CANONICAL_MARKETS),
    "mlb": {},
}

FD_TAB_MARKETS_BY_LEAGUE: dict[str, dict[str, tuple[str, ...]]] = {
    "nba": {tab: (market,) for tab, market in FD_TAB_CANONICAL_MARKETS.items()},
    "mlb": dict(FD_MLB_TAB_MARKETS),
}

FD_EXTENDED_OU_MARKETS_BY_LEAGUE: dict[str, tuple[str, ...]] = {
    "nba": FD_EXTENDED_OU_MARKETS,
    "mlb": (),
}

FD_MLB_MILESTONE_MARKETS: tuple[str, ...] = (
    "hits",
    "total_bases",
    "runs",
    "rbi",
    "h+r+rbi",
)

FD_DEFAULT_SCRAPE_MARKETS_BY_LEAGUE: dict[str, tuple[str, ...]] = {
    "nba": FD_DEFAULT_SCRAPE_MARKETS,
    "mlb": FD_MLB_DEFAULT_SCRAPE_MARKETS,
}

FD_MILESTONE_MARKETS_BY_LEAGUE: dict[str, tuple[str, ...]] = {
    "mlb": FD_MLB_MILESTONE_MARKETS,
}

_STAT_SUFFIX_TO_CANONICAL_BY_LEAGUE: dict[str, tuple[tuple[str, str], ...]] = {
    "nba": _STAT_SUFFIX_TO_CANONICAL_NBA,
    "mlb": _STAT_SUFFIX_TO_CANONICAL_MLB,
}

# PLAYER_A_TOTAL_POINTS / PLAYER_A_ALT_TOTAL_PTS_+_REB_+_AST (NBA)
FD_PLAYER_OU_MARKET_RE = re.compile(
    r"^PLAYER_[A-Z]_(?P<alt>ALT_)?TOTAL_(?P<stat>.+)$"
)

# PITCHER_C_TOTAL_STRIKEOUTS (MLB main O/U)
FD_PITCHER_OU_MARKET_RE = re.compile(
    r"^PITCHER_[A-Z]_TOTAL_(?P<stat>.+)$"
)

# BATTER_A_TOTAL_HITS (MLB batter O/U when FD offers them)
FD_BATTER_OU_MARKET_RE = re.compile(
    r"^BATTER_[A-Z]_TOTAL_(?P<stat>.+)$"
)

# TO_RECORD_2+_TOTAL_BASES / TO_RECORD_A_RUN / TO_RECORD_AN_RBI (MLB milestones)
FD_TO_RECORD_MILESTONE_RE = re.compile(
    r"^TO_RECORD_(?P<threshold>\d+)\+_(?P<stat>.+)$"
)
FD_TO_RECORD_SINGULAR_MILESTONE_RE = re.compile(
    r"^TO_RECORD_(?:A|AN)_(?P<stat>.+)$"
)
FD_PLAYER_TO_RECORD_HIT_RE = re.compile(r"^PLAYER_TO_RECORD_A_HIT$")
FD_PLAYER_TO_RECORD_HITS_RE = re.compile(
    r"^PLAYER_TO_RECORD_(?P<threshold>\d+)\+_HITS$"
)
FD_PLAYER_TO_RECORD_HRR_RE = re.compile(
    r"^PLAYER_TO_RECORD_(?P<threshold>\d+)\+_HITS\+RUNS\+RBIS$"
)


def _league_key(league: str) -> str:
    return league.lower()


def tab_canonical_markets_for_league(league: str = "nba") -> dict[str, str]:
    return FD_TAB_CANONICAL_MARKETS_BY_LEAGUE[_league_key(league)]


def tab_markets_for_league(league: str = "nba") -> dict[str, tuple[str, ...]]:
    return FD_TAB_MARKETS_BY_LEAGUE[_league_key(league)]


def extended_ou_markets_for_league(league: str = "nba") -> tuple[str, ...]:
    return FD_EXTENDED_OU_MARKETS_BY_LEAGUE[_league_key(league)]


def default_scrape_markets_for_league(league: str = "nba") -> tuple[str, ...]:
    return FD_DEFAULT_SCRAPE_MARKETS_BY_LEAGUE[_league_key(league)]


def milestone_markets_for_league(league: str = "nba") -> tuple[str, ...]:
    return FD_MILESTONE_MARKETS_BY_LEAGUE.get(_league_key(league), ())


def milestone_threshold_to_line(threshold: int) -> float:
    """Map FD N+ milestone to Betr half-point line (N+ -> line N - 0.5)."""
    return float(threshold) - 0.5


def canonical_to_tab_for_league(league: str = "nba") -> dict[str, str]:
    key = _league_key(league)
    if key == "nba":
        return dict(FD_CANONICAL_TO_TAB)
    mapping: dict[str, str] = {}
    for tab, markets in tab_markets_for_league(league).items():
        for market in markets:
            mapping[market] = tab
    return mapping


def is_multi_market_tab(tab: str, *, league: str = "nba") -> bool:
    """True when one tab fetch can return multiple canonical O/U markets."""
    key = _league_key(league)
    if key == "mlb":
        return tab in tab_markets_for_league(league)
    return tab == FD_SGP_TAB


def canonical_market_for_tab(tab: str, *, league: str = "nba") -> str | None:
    return tab_canonical_markets_for_league(league).get(tab)


def tab_for_canonical_market(market: str, *, league: str = "nba") -> str | None:
    return canonical_to_tab_for_league(league).get(market)


def _canonical_for_stat_suffix(stat_suffix: str, *, league: str = "nba") -> str | None:
    for suffix, market in _STAT_SUFFIX_TO_CANONICAL_BY_LEAGUE[_league_key(league)]:
        if stat_suffix == suffix:
            return market
    return None


def parse_player_milestone_market_type(
    market_type: str,
    *,
    league: str = "nba",
) -> tuple[str, int] | None:
    """
    Return (canonical_market, threshold) for a FanDuel MLB milestone marketType.

    Returns None for O/U boards, unmapped stats, and non-MLB leagues.
    """
    if _league_key(league) != "mlb":
        return None

    text = market_type or ""

    match = FD_PLAYER_TO_RECORD_HIT_RE.match(text)
    if match:
        return "hits", 1

    match = FD_PLAYER_TO_RECORD_HITS_RE.match(text)
    if match:
        return "hits", int(match.group("threshold"))

    match = FD_PLAYER_TO_RECORD_HRR_RE.match(text)
    if match:
        return "h+r+rbi", int(match.group("threshold"))

    match = FD_TO_RECORD_MILESTONE_RE.match(text)
    if match:
        stat = _canonical_for_stat_suffix(match.group("stat"), league=league)
        if not stat:
            return None
        return stat, int(match.group("threshold"))

    match = FD_TO_RECORD_SINGULAR_MILESTONE_RE.match(text)
    if match:
        stat_suffix = match.group("stat")
        if stat_suffix == "RUN":
            stat_suffix = "RUNS"
        stat = _canonical_for_stat_suffix(stat_suffix, league=league)
        if not stat:
            return None
        return stat, 1

    return None


def parse_player_ou_market_type(
    market_type: str,
    *,
    league: str = "nba",
) -> tuple[str, bool] | None:
    """
    Return (canonical_market, is_alt) for a FanDuel player O/U marketType.

    Returns None for milestones, game lines, quarter props, and other non-O/U boards.
    """
    text = market_type or ""
    key = _league_key(league)

    if key == "nba":
        match = FD_PLAYER_OU_MARKET_RE.match(text)
        if not match:
            return None
        stat = _canonical_for_stat_suffix(match.group("stat"), league=league)
        if not stat:
            return None
        return stat, bool(match.group("alt"))

    for pattern in (FD_PITCHER_OU_MARKET_RE, FD_BATTER_OU_MARKET_RE):
        match = pattern.match(text)
        if not match:
            continue
        stat = _canonical_for_stat_suffix(match.group("stat"), league=league)
        if not stat:
            return None
        return stat, False

    return None


def is_player_milestone_market_for_tab(
    market_type: str,
    tab: str,
    *,
    league: str = "nba",
) -> bool:
    """True when marketType is a milestone ladder row for this tab's stat family."""
    parsed = parse_player_milestone_market_type(market_type, league=league)
    if not parsed:
        return False
    market, _ = parsed
    if is_multi_market_tab(tab, league=league):
        return market in tab_markets_for_league(league).get(tab, ()) or market in milestone_markets_for_league(league)
    return market == canonical_market_for_tab(tab, league=league)


def is_player_ou_market_for_tab(
    market_type: str,
    tab: str,
    *,
    league: str = "nba",
) -> bool:
    """True when marketType is a main or alt player O/U ladder for this tab's stat."""
    parsed = parse_player_ou_market_type(market_type, league=league)
    if not parsed:
        return False
    market, _ = parsed
    if is_multi_market_tab(tab, league=league):
        return market in tab_markets_for_league(league).get(tab, ())
    return market == canonical_market_for_tab(tab, league=league)


def is_extended_ou_market(market: str, *, league: str = "nba") -> bool:
    return market in extended_ou_markets_for_league(league)


def is_core_ou_market(market: str, *, league: str = "nba") -> bool:
    return market in canonical_to_tab_for_league(league)


def known_markets_for_league(league: str = "nba") -> frozenset[str]:
    key = _league_key(league)
    markets = set(default_scrape_markets_for_league(key))
    markets.update(canonical_to_tab_for_league(key))
    markets.update(extended_ou_markets_for_league(key))
    return frozenset(markets)
