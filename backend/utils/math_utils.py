"""Odds conversion and de-vigging formulas."""


def decimal_to_american(decimal_price):
    """
    Converts a decimal payout into standard American odds for EV math.
    Used primarily for Dabble Lightnings and Shields.
    """
    try:
        decimal_price = float(decimal_price)
        if decimal_price >= 2.0:
            return round((decimal_price - 1) * 100)
        if decimal_price > 1.0:
            return round(-100 / (decimal_price - 1))
    except (ValueError, TypeError):
        pass
    return -122


def american_to_implied(odds: int) -> float:
    """Convert American odds to implied probability."""
    if odds < 0:
        return abs(odds) / (abs(odds) + 100)
    return 100 / (odds + 100)


def multiplicative_devig(over_odds: int, under_odds: int) -> tuple[float, float]:
    """Remove vig using the multiplicative method and return fair over/under probabilities."""
    over_implied = american_to_implied(over_odds)
    under_implied = american_to_implied(under_odds)
    total_implied = over_implied + under_implied
    return over_implied / total_implied, under_implied / total_implied
