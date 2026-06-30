"""Registry of sharp-book resolution strategies for multi-book EV assembly."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

OuResolution = Literal["full", "exact_only"]


@dataclass(frozen=True)
class SharpBookConfig:
    name: str
    ev_priority: int  # lower = preferred EV source
    ou_resolution: OuResolution
    # "full"       = DK  (exact + interpolate + extrapolate + milestone fallback)
    # "exact_only" = FD/ESPN (exact O/U only + milestone fallback; no interp/extrap)
    milestone_fallback: bool
    hold_own_book_only: bool
    # True  = use only own-book O/U hold for milestone devig (DK, FD)
    # False = prefer own-book O/U hold; fall back to cross-book when absent (ESPN)


SHARP_BOOKS: list[SharpBookConfig] = [
    SharpBookConfig(
        "DraftKings",
        ev_priority=1,
        ou_resolution="full",
        milestone_fallback=True,
        hold_own_book_only=True,
    ),
    SharpBookConfig(
        "FanDuel",
        ev_priority=2,
        ou_resolution="exact_only",
        milestone_fallback=True,
        hold_own_book_only=True,
    ),
    SharpBookConfig(
        "ESPN",
        ev_priority=3,
        ou_resolution="exact_only",
        milestone_fallback=True,
        hold_own_book_only=False,
    ),
]

SHARP_BOOK_BY_NAME: dict[str, SharpBookConfig] = {b.name: b for b in SHARP_BOOKS}
