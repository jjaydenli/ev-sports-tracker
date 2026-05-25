import pytest

from utils.math_utils import (
    BETR_STANDARD_BREAKEVEN_ODDS,
    american_to_implied,
    calculate_ev,
    calculate_ev_percent,
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
