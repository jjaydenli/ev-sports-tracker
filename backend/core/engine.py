"""EV execution calculations across matched props."""

from utils.math_utils import american_to_implied, multiplicative_devig


def build_prop_key(prop: dict) -> str:
    """Build a stable lookup key for cross-book matching."""
    return f"{prop['player']}_{prop['market']}_{prop['line']}"


def calculate_ev(fair_prob: float, dfs_implied_prob: float) -> float:
    """Return expected value as fair probability minus DFS breakeven probability."""
    return fair_prob - dfs_implied_prob


def find_ev_opportunities(
    dfs_props: list[dict],
    sportsbook_props: list[dict],
    dfs_breakeven_odds: int = -122,
) -> list[dict]:
    """
    Match props across books and compute +EV opportunities using multiplicative de-vig.
    """
    sportsbook_lookup = {build_prop_key(item): item for item in sportsbook_props}
    dfs_breakeven_prob = american_to_implied(dfs_breakeven_odds)
    opportunities = []

    for dfs_prop in dfs_props:
        key = build_prop_key(dfs_prop)
        sportsbook_prop = sportsbook_lookup.get(key)
        if not sportsbook_prop:
            continue

        over_odds = sportsbook_prop.get("over_odds")
        under_odds = sportsbook_prop.get("under_odds")
        if over_odds is None or under_odds is None:
            continue

        fair_over, _fair_under = multiplicative_devig(over_odds, under_odds)
        ev = calculate_ev(fair_over, dfs_breakeven_prob)
        if ev > 0:
            opportunities.append(
                {
                    "player": dfs_prop["player"],
                    "market": dfs_prop["market"],
                    "line": dfs_prop["line"],
                    "fair_prob": round(fair_over, 4),
                    "dfs_breakeven_prob": round(dfs_breakeven_prob, 4),
                    "ev": round(ev, 4),
                }
            )

    return opportunities
