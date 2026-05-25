"""Odds conversion, de-vigging, and EV formulas."""

BETR_STANDARD_BREAKEVEN_ODDS = -122


def decimal_to_american(decimal_price: float) -> int:
    """Convert decimal payout to American odds."""
    try:
        decimal_price = float(decimal_price)
        if decimal_price >= 2.0:
            return round((decimal_price - 1) * 100)
        if decimal_price > 1.0:
            return round(-100 / (decimal_price - 1))
    except (ValueError, TypeError):
        pass
    return BETR_STANDARD_BREAKEVEN_ODDS


def american_to_implied(odds: int) -> float:
    """Convert American odds to implied probability."""
    if odds < 0:
        return abs(odds) / (abs(odds) + 100)
    return 100 / (odds + 100)


def implied_to_american(prob: float) -> int:
    """Convert implied probability to American odds."""
    if prob <= 0 or prob >= 1:
        raise ValueError(f"probability must be between 0 and 1, got {prob}")
    if prob >= 0.5:
        return round(-100 * prob / (1 - prob))
    return round(100 * (1 - prob) / prob)


def multiplicative_devig(over_odds: int, under_odds: int) -> tuple[float, float]:
    """Remove vig via the multiplicative method; return fair over/under probabilities."""
    over_implied = american_to_implied(over_odds)
    under_implied = american_to_implied(under_odds)
    total_implied = over_implied + under_implied
    if total_implied <= 0:
        raise ValueError("invalid odds: total implied probability must be positive")
    return over_implied / total_implied, under_implied / total_implied


def calculate_ev(fair_prob: float, breakeven_prob: float) -> float:
    """Return EV as fair probability minus breakeven implied probability."""
    return fair_prob - breakeven_prob


def calculate_ev_percent(fair_prob: float, breakeven_prob: float) -> float:
    """Return EV as a percentage (e.g. 3.25 means +3.25% edge)."""
    return calculate_ev(fair_prob, breakeven_prob) * 100


def implied_prob_to_pct(prob: float) -> float:
    """Convert implied probability (0–1) to a percentage (e.g. 0.5604 -> 56.04)."""
    return round(prob * 100, 2)
