"""Betr integer (flat) lines where a tie voids the DFS leg."""

from __future__ import annotations

# v1 heuristic push rates by market (tune with historical data).
DEFAULT_PUSH_PROBABILITY = 0.06
PUSH_PROBABILITY_BY_MARKET: dict[str, float] = {
    "points": 0.05,
    "rebounds": 0.08,
    "assists": 0.07,
    "threes": 0.06,
    "steals": 0.09,
    "blocks": 0.09,
    "stl+blk": 0.08,
    "pra": 0.04,
    "pts+reb": 0.05,
    "pts+ast": 0.05,
    "reb+ast": 0.06,
}


def is_flat_line(line: float) -> bool:
    """True when the line is an integer (push possible on Betr)."""
    return float(line) == int(line)


def line_kind(line: float) -> str:
    return "flat" if is_flat_line(line) else "half_point"


def push_probability(market: str) -> float:
    return PUSH_PROBABILITY_BY_MARKET.get(market, DEFAULT_PUSH_PROBABILITY)


def adjusted_breakeven_probability(
    breakeven_prob: float,
    market: str,
) -> float:
    """
    Raise the win probability required when a push voids the leg.

    v1: scale breakeven up by 1 / (1 - push_prob).
    """
    push_prob = push_probability(market)
    if push_prob <= 0:
        return breakeven_prob
    adjusted = breakeven_prob / (1 - push_prob)
    return min(max(adjusted, breakeven_prob), 0.99)
