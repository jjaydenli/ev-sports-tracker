"""Platform-agnostic normalized prop schemas."""

from typing import TypedDict


class NormalizedProp(TypedDict, total=False):
    sportsbook: str
    player: str
    market: str
    line: float
    prop_type: str
    over_odds: int | None
    under_odds: int | None
    raw_multiplier: float | None
