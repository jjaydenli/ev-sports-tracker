"""Pure probability math for line adjustment (logit, devig, extrapolation)."""

from __future__ import annotations

import math
from typing import Any

from utils.math_utils import american_to_implied, multiplicative_devig

# Logit shift applied per 1.0 point of line gap (target - anchor) by market.
EXTRAPOLATION_LOGIT_SHIFT_PER_POINT: dict[str, float] = {
    "points": 0.12,
    "rebounds": 0.10,
    "assists": 0.10,
    "threes": 0.11,
    "steals": 0.11,
    "blocks": 0.11,
    "stl+blk": 0.10,
    "pra": 0.09,
    "pts+reb": 0.09,
    "pts+ast": 0.09,
    "reb+ast": 0.09,
    "hits": 0.08,
    "total_bases": 0.08,
    "h+r+rbi": 0.08,
    "singles": 0.08,
    "default": 0.08,
}

def _logit(probability: float) -> float:
    clamped = min(max(probability, 1e-6), 1 - 1e-6)
    return math.log(clamped / (1 - clamped))


def _inv_logit(value: float) -> float:
    return 1 / (1 + math.exp(-value))


def _interp_logit(p_low: float, p_high: float, weight_high: float) -> float:
    """Linear interpolation in logit space; weight_high=1 -> p_high."""
    weight_high = min(max(weight_high, 0.0), 1.0)
    low = _logit(p_low)
    high = _logit(p_high)
    return _inv_logit((1 - weight_high) * low + weight_high * high)


def _shift_per_point(market: str) -> float:
    return EXTRAPOLATION_LOGIT_SHIFT_PER_POINT.get(
        market, EXTRAPOLATION_LOGIT_SHIFT_PER_POINT["default"]
    )
def estimate_ou_hold(
    ou_ladders: dict[str, dict[str, dict[float, dict[str, Any]]]],
    pm_key: str,
    *,
    preferred_book: str | None = None,
    source_book_only: bool = False,
) -> float | None:
    """Average two-sided hold for a player|market across O/U rows; None when no O/U exists."""
    book_order = list(ou_ladders.keys())
    if preferred_book and preferred_book in ou_ladders:
        book_order = [preferred_book] + [
            book for book in book_order if book != preferred_book
        ]
    if source_book_only and preferred_book:
        book_order = [preferred_book]

    holds: list[float] = []
    for book in book_order:
        lines = ou_ladders.get(book, {}).get(pm_key)
        if not lines:
            continue
        for row in lines.values():
            over_odds = row.get("over_odds")
            under_odds = row.get("under_odds")
            if over_odds is None or under_odds is None:
                continue
            over_implied = american_to_implied(int(over_odds))
            under_implied = american_to_implied(int(under_odds))
            holds.append(over_implied + under_implied - 1.0)
        if holds:
            return sum(holds) / len(holds)
    return None


def _contiguous_milestone_segment(
    sorted_lines: list[float],
    target_line: float,
    *,
    step: float = 1.0,
) -> list[float] | None:
    """Return the contiguous ladder segment containing target_line, or None."""
    if target_line not in sorted_lines:
        return None
    idx = sorted_lines.index(target_line)
    start = idx
    while start > 0 and abs(sorted_lines[start] - sorted_lines[start - 1] - step) < 1e-9:
        start -= 1
    end = idx
    while (
        end < len(sorted_lines) - 1
        and abs(sorted_lines[end + 1] - sorted_lines[end] - step) < 1e-9
    ):
        end += 1
    segment = sorted_lines[start : end + 1]
    if len(segment) >= 2:
        return segment
    return None


def _survival_at_line(
    segment: list[float],
    lines: dict[float, dict[str, Any]],
    target_line: float,
) -> float:
    """Fair P(X >= threshold) from renormalized PMF masses on a milestone ladder."""
    survivals = [american_to_implied(lines[line]["over_odds"]) for line in segment]
    masses = [1.0 - survivals[0]]
    masses.extend(s - survivals[i + 1] for i, s in enumerate(survivals[:-1]))
    masses.append(survivals[-1])
    masses = [max(0.0, mass) for mass in masses]
    total = sum(masses)
    if total <= 0:
        return american_to_implied(lines[target_line]["over_odds"])
    masses = [mass / total for mass in masses]
    target_idx = segment.index(target_line)
    if target_idx + 1 >= len(masses):
        return masses[-1]
    return sum(masses[target_idx + 1 :])


def devig_milestone_fair_over(
    lines: dict[float, dict[str, Any]],
    target_line: float,
    *,
    market: str,
    ou_hold: float | None,
) -> tuple[float, str]:
    """
    De-vig a milestone over-only price via ladder normalization or hold shrink.

    Returns (fair_over_probability, method_name).
    """
    from config.settings import MILESTONE_ASSUMED_HOLD

    _ = market  # reserved for market-specific ladder steps if needed later
    sorted_lines = sorted(lines.keys())
    segment = _contiguous_milestone_segment(sorted_lines, target_line)
    if segment is not None:
        return _survival_at_line(segment, lines, target_line), "ladder_normalized"

    raw = american_to_implied(lines[target_line]["over_odds"])
    hold = ou_hold if ou_hold is not None else MILESTONE_ASSUMED_HOLD
    return raw * (1.0 - hold / 2.0), "hold_shrink"


def _fair_probs_from_odds(over_odds: int, under_odds: int) -> tuple[float, float]:
    return multiplicative_devig(over_odds, under_odds)


def _fair_over_from_milestone(over_odds: int) -> float:
    return american_to_implied(over_odds)


def _odds_from_fair_probs(fair_over: float, fair_under: float) -> tuple[int, int]:
    from utils.math_utils import implied_to_american

    return implied_to_american(fair_over), implied_to_american(fair_under)


def _extrapolate_fair_probs(
    fair_over: float,
    fair_under: float,
    *,
    anchor_line: float,
    target_line: float,
    market: str,
) -> tuple[float, float]:
    """
    Shift fair probs from anchor_line to target_line.

    Lower target vs anchor -> higher over / lower under probability.
    """
    gap = anchor_line - target_line
    shift = _shift_per_point(market) * gap
    fair_over = _inv_logit(_logit(fair_over) + shift)
    fair_under = _inv_logit(_logit(fair_under) - shift)
    total = fair_over + fair_under
    if total <= 0:
        return fair_over, fair_under
    return fair_over / total, fair_under / total


def _extrapolate_milestone_fair_over(
    fair_over: float,
    *,
    anchor_line: float,
    target_line: float,
    market: str,
) -> float:
    gap = anchor_line - target_line
    shift = _shift_per_point(market) * gap
    return _inv_logit(_logit(fair_over) + shift)

