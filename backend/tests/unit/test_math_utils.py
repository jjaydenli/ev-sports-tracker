import pytest

from config.settings import MILESTONE_ASSUMED_HOLD, MILESTONE_MIN_FAIR_OVER
from core.line_adjustment import devig_milestone_fair_over
from utils.math_utils import (
    BETR_STANDARD_BREAKEVEN_ODDS,
    american_to_implied,
    calculate_ev,
    calculate_ev_percent,
    decimal_to_american,
    implied_prob_to_pct,
    implied_to_american,
    multiplicative_devig,
)


def test_american_to_implied_negative_odds():
    assert american_to_implied(-120) == pytest.approx(0.5454545, rel=1e-4)


def test_american_to_implied_positive_odds():
    assert american_to_implied(100) == 0.5


def test_multiplicative_devig_removes_vig():
    fair_over, fair_under = multiplicative_devig(-110, -110)

    assert fair_over == pytest.approx(0.5, rel=1e-4)
    assert fair_under == pytest.approx(0.5, rel=1e-4)
    assert fair_over + fair_under == pytest.approx(1.0, rel=1e-4)


def test_calculate_ev_positive_edge():
    breakeven = american_to_implied(BETR_STANDARD_BREAKEVEN_ODDS)
    fair_over, _ = multiplicative_devig(-140, 120)

    assert calculate_ev(fair_over, breakeven) > 0
    assert calculate_ev_percent(fair_over, breakeven) == pytest.approx(
        calculate_ev(fair_over, breakeven) * 100
    )


def test_implied_prob_to_pct():
    assert implied_prob_to_pct(0.5604) == 56.04
    assert implied_prob_to_pct(american_to_implied(-120)) == 54.55


def test_implied_to_american_round_trip():
    odds = -111
    prob = american_to_implied(odds)
    assert implied_to_american(prob) == odds


# ---------------------------------------------------------------------------
# Phase 9 — known-answer edge tables
# ---------------------------------------------------------------------------

# american_to_implied — exact formula checks across range including extremes
@pytest.mark.parametrize(
    "odds,expected",
    [
        (-100, 0.5),
        (+100, 0.5),
        (-110, 110 / 210),
        (-120, 120 / 220),
        (-200, 200 / 300),
        (+200, 100 / 300),
        (-10_000, 10_000 / 10_100),   # extreme negative → near-1
        (+10_000, 100 / 10_100),       # extreme positive → near-0
    ],
)
def test_american_to_implied_known_values(odds: int, expected: float) -> None:
    assert american_to_implied(odds) == pytest.approx(expected, rel=1e-9)


# implied_to_american — exact round-trip at representative odds
@pytest.mark.parametrize("odds", [-200, -150, -120, -110, -105, 105, 110, 120, 150, 200])
def test_implied_to_american_table_round_trip(odds: int) -> None:
    assert implied_to_american(american_to_implied(odds)) == odds


# implied_to_american — boundary raises on out-of-range prob
@pytest.mark.parametrize("prob", [0.0, 1.0, -0.001, 1.001])
def test_implied_to_american_invalid_raises(prob: float) -> None:
    with pytest.raises(ValueError):
        implied_to_american(prob)


# decimal_to_american — known values and fallback on bad input
@pytest.mark.parametrize(
    "decimal_price,expected",
    [
        (2.0, 100),       # even money
        (3.0, 200),       # +200
        (1.5, -200),      # -200
        (1.25, -400),     # -400
        (2.5, 150),       # +150
    ],
)
def test_decimal_to_american_known_values(decimal_price: float, expected: int) -> None:
    assert decimal_to_american(decimal_price) == expected


def test_decimal_to_american_invalid_returns_fallback() -> None:
    assert decimal_to_american("not-a-number") == BETR_STANDARD_BREAKEVEN_ODDS
    assert decimal_to_american(1.0) == BETR_STANDARD_BREAKEVEN_ODDS  # ≤1.0 is invalid


# multiplicative_devig — known-answer table
@pytest.mark.parametrize(
    "over_odds,under_odds",
    [
        (-110, -110),    # balanced
        (-120, +100),    # slight over-lean
        (-200, +170),    # heavy favourite
        (-105, -115),    # typical juice spread
    ],
)
def test_multiplicative_devig_sums_to_one_table(over_odds: int, under_odds: int) -> None:
    fair_over, fair_under = multiplicative_devig(over_odds, under_odds)
    assert fair_over + fair_under == pytest.approx(1.0, rel=1e-9)
    assert 0.0 < fair_over < 1.0
    assert 0.0 < fair_under < 1.0


def test_multiplicative_devig_exact_symmetric() -> None:
    fair_over, fair_under = multiplicative_devig(-110, -110)
    assert fair_over == pytest.approx(0.5, rel=1e-9)
    assert fair_under == pytest.approx(0.5, rel=1e-9)


def test_multiplicative_devig_exact_asymmetric() -> None:
    # -200/+170: over implied = 2/3, under implied = 100/270
    o_imp = 200 / 300
    u_imp = 100 / 270
    total = o_imp + u_imp
    fair_over, fair_under = multiplicative_devig(-200, 170)
    assert fair_over == pytest.approx(o_imp / total, rel=1e-9)
    assert fair_under == pytest.approx(u_imp / total, rel=1e-9)


# calculate_ev — sign boundary (zero crossing)
def test_calculate_ev_zero_at_breakeven() -> None:
    breakeven = american_to_implied(BETR_STANDARD_BREAKEVEN_ODDS)
    assert calculate_ev(breakeven, breakeven) == pytest.approx(0.0, abs=1e-12)


def test_calculate_ev_positive_just_above_breakeven() -> None:
    breakeven = american_to_implied(BETR_STANDARD_BREAKEVEN_ODDS)
    assert calculate_ev(breakeven + 0.001, breakeven) > 0


def test_calculate_ev_negative_just_below_breakeven() -> None:
    breakeven = american_to_implied(BETR_STANDARD_BREAKEVEN_ODDS)
    assert calculate_ev(breakeven - 0.001, breakeven) < 0


# ---------------------------------------------------------------------------
# Milestone gate boundary (MILESTONE_MIN_FAIR_OVER = 0.6154)
# ---------------------------------------------------------------------------

# Single-rung ladder → hold_shrink path:
#   fair_over = raw_implied * (1 - MILESTONE_ASSUMED_HOLD / 2)
# Admission threshold in terms of raw implied:
#   raw_threshold = MILESTONE_MIN_FAIR_OVER / (1 - MILESTONE_ASSUMED_HOLD / 2)


def _single_rung(over_odds: int) -> dict:
    return {0.5: {"over_odds": over_odds, "is_main_line": True}}


def test_devig_milestone_fair_over_uses_hold_shrink_for_single_rung() -> None:
    """Single rung → no contiguous segment → hold_shrink method is used."""
    _, method = devig_milestone_fair_over(_single_rung(-180), 0.5, market="hits", ou_hold=None)
    assert method == "hold_shrink"


def test_devig_milestone_fair_over_hold_shrink_exact_value() -> None:
    raw = american_to_implied(-180)
    expected = raw * (1.0 - MILESTONE_ASSUMED_HOLD / 2.0)
    fair_over, _ = devig_milestone_fair_over(
        _single_rung(-180), 0.5, market="hits", ou_hold=None
    )
    assert fair_over == pytest.approx(expected, rel=1e-9)


def test_devig_milestone_fair_over_admitted_when_above_gate() -> None:
    # Need raw such that raw * (1 - ASSUMED_HOLD/2) >= MILESTONE_MIN_FAIR_OVER
    # Using -400: raw = 400/500 = 0.8; fair = 0.8 * 0.97 = 0.776 >> 0.6154
    fair_over, _ = devig_milestone_fair_over(
        _single_rung(-400), 0.5, market="hits", ou_hold=None
    )
    assert fair_over >= MILESTONE_MIN_FAIR_OVER


def test_devig_milestone_fair_over_not_admitted_when_below_gate() -> None:
    # Using -120: raw = 120/220 ≈ 0.5455; fair = 0.5455 * 0.97 ≈ 0.529 << 0.6154
    fair_over, _ = devig_milestone_fair_over(
        _single_rung(-120), 0.5, market="hits", ou_hold=None
    )
    assert fair_over < MILESTONE_MIN_FAIR_OVER


def test_devig_milestone_fair_over_ladder_normalized_for_two_rungs() -> None:
    """Two-rung contiguous ladder → ladder_normalized (not hold_shrink)."""
    lines = {
        0.5: {"over_odds": -400, "is_main_line": False},
        1.5: {"over_odds": -200, "is_main_line": True},
    }
    _, method = devig_milestone_fair_over(lines, 0.5, market="hits", ou_hold=None)
    assert method == "ladder_normalized"


def test_devig_milestone_fair_over_ladder_result_in_unit_interval() -> None:
    """Ladder-normalized result is a valid probability in (0, 1)."""
    lines = {
        0.5: {"over_odds": -400, "is_main_line": False},
        1.5: {"over_odds": -200, "is_main_line": True},
    }
    fair_over, _ = devig_milestone_fair_over(lines, 0.5, market="hits", ou_hold=None)
    assert 0.0 < fair_over < 1.0
    assert fair_over >= MILESTONE_MIN_FAIR_OVER
