"""Property-based tests for pure numeric functions using Hypothesis.

Invariants only — no engine behaviour changes implied.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from core.flat_line import adjusted_breakeven_probability
from core.line_adjustment import _interp_logit, _inv_logit, _logit, devig_milestone_fair_over
from utils.math_utils import american_to_implied, implied_to_american, multiplicative_devig

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_american_odds = st.one_of(
    st.integers(min_value=-10_000, max_value=-101),
    # Exclude +100: american_to_implied(100) = 0.5, but implied_to_american(0.5) = -100 (off by 200).
    # +100 and -100 both encode 50%; round-trip across the ±boundary is undefined.
    st.integers(min_value=101, max_value=10_000),
)

_prob = st.floats(min_value=1e-4, max_value=1 - 1e-4)

_push_prob = st.floats(min_value=0.0, max_value=0.5, allow_nan=False)

_breakeven = st.floats(min_value=0.01, max_value=0.98, allow_nan=False)


# ---------------------------------------------------------------------------
# multiplicative_devig
# ---------------------------------------------------------------------------


@given(_american_odds, _american_odds)
@settings(max_examples=500)
def test_multiplicative_devig_sums_to_one(over: int, under: int) -> None:
    fair_over, fair_under = multiplicative_devig(over, under)
    assert abs(fair_over + fair_under - 1.0) < 1e-9


@given(_american_odds, _american_odds)
@settings(max_examples=500)
def test_multiplicative_devig_both_in_unit_interval(over: int, under: int) -> None:
    fair_over, fair_under = multiplicative_devig(over, under)
    assert 0.0 <= fair_over <= 1.0
    assert 0.0 <= fair_under <= 1.0


# ---------------------------------------------------------------------------
# american_to_implied / implied_to_american round-trip
# ---------------------------------------------------------------------------


@given(_american_odds)
@settings(max_examples=500)
def test_american_round_trip(odds: int) -> None:
    """implied_to_american(american_to_implied(odds)) ≈ odds within ±1."""
    prob = american_to_implied(odds)
    recovered = implied_to_american(prob)
    # American odds are integers; round-trip may differ by ±1 due to rounding.
    assert abs(recovered - odds) <= 1


@given(_prob)
@settings(max_examples=500)
def test_implied_round_trip(prob: float) -> None:
    """american_to_implied(implied_to_american(p)) ≈ p within tolerance."""
    odds = implied_to_american(prob)
    recovered = american_to_implied(odds)
    assert abs(recovered - prob) < 0.005


# ---------------------------------------------------------------------------
# _logit / _inv_logit round-trip
# ---------------------------------------------------------------------------


@given(_prob)
@settings(max_examples=500)
def test_logit_round_trip(p: float) -> None:
    """_inv_logit(_logit(p)) ≈ p."""
    assert abs(_inv_logit(_logit(p)) - p) < 1e-9


@given(_prob)
@settings(max_examples=500)
def test_inv_logit_round_trip(p: float) -> None:
    """_logit(_inv_logit(logit(p))) round-trips logit space."""
    logit_val = _logit(p)
    assert abs(_logit(_inv_logit(logit_val)) - logit_val) < 1e-9


# ---------------------------------------------------------------------------
# _interp_logit — monotonic and bounded between anchors
# ---------------------------------------------------------------------------


@given(
    st.floats(min_value=0.05, max_value=0.45, allow_nan=False),
    st.floats(min_value=0.55, max_value=0.95, allow_nan=False),
    st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)
@settings(max_examples=500)
def test_interp_logit_bounded_between_anchors(
    p_low: float, p_high: float, weight_high: float
) -> None:
    """Result is always between p_low and p_high (within floating-point epsilon)."""
    result = _interp_logit(p_low, p_high, weight_high)
    assert (p_low - 1e-10) <= result <= (p_high + 1e-10)


@given(
    st.floats(min_value=0.05, max_value=0.45, allow_nan=False),
    st.floats(min_value=0.55, max_value=0.95, allow_nan=False),
)
@settings(max_examples=500)
def test_interp_logit_monotonic_in_weight(p_low: float, p_high: float) -> None:
    """Higher weight_high → higher result (monotonically increasing in weight)."""
    r0 = _interp_logit(p_low, p_high, 0.0)
    r_half = _interp_logit(p_low, p_high, 0.5)
    r1 = _interp_logit(p_low, p_high, 1.0)
    assert r0 <= r_half <= r1


# ---------------------------------------------------------------------------
# adjusted_breakeven_probability
# ---------------------------------------------------------------------------


@given(_breakeven, st.sampled_from(["points", "rebounds", "assists", "hits", "threes"]))
@settings(max_examples=500)
def test_adjusted_breakeven_ge_raw(base: float, market: str) -> None:
    """Push adjustment can only raise the required win probability."""
    result = adjusted_breakeven_probability(base, market)
    assert result >= base


@given(_breakeven, st.sampled_from(["points", "rebounds", "assists", "hits", "threes"]))
@settings(max_examples=500)
def test_adjusted_breakeven_le_099(base: float, market: str) -> None:
    """Adjusted breakeven is capped at 0.99."""
    result = adjusted_breakeven_probability(base, market)
    assert result <= 0.99


@given(_breakeven)
@settings(max_examples=300)
def test_adjusted_breakeven_monotonic_in_push_prob(base: float) -> None:
    """Higher push probability → equal or higher adjusted breakeven (real function)."""
    # points push_prob=0.05 < rebounds push_prob=0.08 per PUSH_PROBABILITY_BY_MARKET
    result_low = adjusted_breakeven_probability(base, "points")
    result_high = adjusted_breakeven_probability(base, "rebounds")
    assert result_low <= result_high


# ---------------------------------------------------------------------------
# devig_milestone_fair_over
# ---------------------------------------------------------------------------


@given(
    st.integers(min_value=-1000, max_value=-110),
    st.integers(min_value=-500, max_value=-110),
)
@settings(max_examples=300)
def test_devig_milestone_fair_over_unit_interval_two_rung_ladder(
    over_rung1: int, over_rung2: int
) -> None:
    """Two-rung contiguous ladder (0.5, 1.5) → fair_over in [0, 1]."""
    lines: dict[float, dict] = {
        0.5: {"over_odds": over_rung1, "milestone_threshold": 1, "is_main_line": True},
        1.5: {"over_odds": over_rung2, "milestone_threshold": 2, "is_main_line": False},
    }
    fair_over, method = devig_milestone_fair_over(
        lines, 0.5, market="hits", ou_hold=None
    )
    assert 0.0 <= fair_over <= 1.0
    assert method == "ladder_normalized"


@given(
    st.integers(min_value=-1000, max_value=-110),
    st.floats(min_value=0.0, max_value=0.25, allow_nan=False),
)
@settings(max_examples=300)
def test_devig_milestone_fair_over_hold_shrink_unit_interval(
    over_odds: int, ou_hold: float
) -> None:
    """Single-entry ladder triggers hold_shrink path → fair_over in [0, 1]."""
    lines: dict[float, dict] = {
        1.5: {"over_odds": over_odds, "milestone_threshold": 2, "is_main_line": True},
    }
    fair_over, method = devig_milestone_fair_over(
        lines, 1.5, market="hits", ou_hold=ou_hold
    )
    assert 0.0 <= fair_over <= 1.0
    assert method == "hold_shrink"


@given(st.integers(min_value=-1000, max_value=-110))
@settings(max_examples=200)
def test_devig_milestone_fair_over_two_rung_result_in_unit_interval(
    over_rung1: int,
) -> None:
    """Two-rung ladder → fair_over stays in [0, 1] for any rung-1 odds."""
    lines: dict[float, dict] = {
        0.5: {"over_odds": over_rung1, "milestone_threshold": 1, "is_main_line": True},
        1.5: {"over_odds": -110, "milestone_threshold": 2, "is_main_line": False},
    }
    fair_over, _ = devig_milestone_fair_over(lines, 0.5, market="hits", ou_hold=None)
    assert 0.0 <= fair_over <= 1.0
