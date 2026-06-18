"""Platform-agnostic normalized prop schemas."""

from typing import Literal, TypedDict

BetSide = Literal["over", "under"]


class NormalizedProp(TypedDict, total=False):
    sportsbook: str
    player: str
    market: str
    line: float
    prop_type: str
    over_odds: int | None
    under_odds: int | None
    raw_multiplier: float | None
    game: str
    team: str
    source_market_id: str


class EvOpportunity(TypedDict):
    league: str
    player: str
    market: str
    line: float
    side: BetSide
    ev: float
    ev_pct: float
    no_vig_implied_pct: float
    no_vig_favored_side: BetSide
    betr_implied_pct: float
    dk_over_odds: int
    dk_under_odds: int
    dfs_sportsbook: str
    sharp_sportsbook: str
