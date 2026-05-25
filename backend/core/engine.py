"""Cross-book EV comparison for Betr (DFS) vs DraftKings (sharp)."""

from __future__ import annotations

from utils.math_utils import (
    BETR_STANDARD_BREAKEVEN_ODDS,
    american_to_implied,
    calculate_ev,
    calculate_ev_percent,
    implied_prob_to_pct,
    multiplicative_devig,
)

DEFAULT_DFS_SPORTSBOOK = "Betr"
DEFAULT_SHARP_SPORTSBOOK = "DraftKings"


def normalize_player_name(name: str) -> str:
    """Normalize player names for cross-book matching."""
    return " ".join(name.strip().lower().split())


def build_prop_key(prop: dict) -> str:
    """Build a stable lookup key for cross-book matching."""
    player = normalize_player_name(prop["player"])
    market = prop["market"]
    line = prop["line"]
    return f"{player}|{market}|{line}"


def index_props_by_key(props: list[dict]) -> dict[str, dict]:
    """Index props by matching key; first occurrence wins on duplicates."""
    indexed: dict[str, dict] = {}
    for prop in props:
        key = build_prop_key(prop)
        if key not in indexed:
            indexed[key] = prop
    return indexed


def _favored_no_vig(fair_over: float, fair_under: float) -> tuple[str, float]:
    """Return the de-vig favored side and its fair probability."""
    if fair_over >= fair_under:
        return "over", fair_over
    return "under", fair_under


def _append_side_opportunity(
    opportunities: list[dict],
    *,
    dfs_prop: dict,
    sharp_prop: dict,
    side: str,
    fair_prob: float,
    breakeven_prob: float,
    fair_over: float,
    fair_under: float,
    dk_over_odds: int,
    dk_under_odds: int,
    min_ev: float,
) -> None:
    ev = calculate_ev(fair_prob, breakeven_prob)
    if ev <= min_ev:
        return

    no_vig_side, no_vig_prob = _favored_no_vig(fair_over, fair_under)

    opportunities.append(
        {
            "player": dfs_prop["player"],
            "market": dfs_prop["market"],
            "line": float(dfs_prop["line"]),
            "side": side,
            "ev": round(ev, 4),
            "ev_pct": round(calculate_ev_percent(fair_prob, breakeven_prob), 2),
            "no_vig_implied_pct": implied_prob_to_pct(no_vig_prob),
            "no_vig_favored_side": no_vig_side,
            "betr_implied_pct": implied_prob_to_pct(breakeven_prob),
            "dk_over_odds": dk_over_odds,
            "dk_under_odds": dk_under_odds,
            "dfs_sportsbook": dfs_prop.get("sportsbook", DEFAULT_DFS_SPORTSBOOK),
            "sharp_sportsbook": sharp_prop.get("sportsbook", DEFAULT_SHARP_SPORTSBOOK),
        }
    )


def find_ev_opportunities(
    dfs_props: list[dict],
    sportsbook_props: list[dict],
    *,
    dfs_breakeven_odds: int = BETR_STANDARD_BREAKEVEN_ODDS,
    min_ev: float = 0.0,
) -> list[dict]:
    """
    Match DFS props to sharp sportsbook lines and return +EV sides.

    Uses multiplicative de-vig on the sharp book's over/under prices. Each matched
    line can produce up to two opportunities (over and under) when fair probability
    exceeds the DFS breakeven implied probability.
    """
    sharp_lookup = index_props_by_key(sportsbook_props)
    breakeven_prob = american_to_implied(dfs_breakeven_odds)
    opportunities: list[dict] = []

    for dfs_prop in dfs_props:
        sharp_prop = sharp_lookup.get(build_prop_key(dfs_prop))
        if not sharp_prop:
            continue

        over_odds = sharp_prop.get("over_odds")
        under_odds = sharp_prop.get("under_odds")
        if over_odds is None or under_odds is None:
            continue

        dk_over = int(over_odds)
        dk_under = int(under_odds)
        fair_over, fair_under = multiplicative_devig(dk_over, dk_under)

        if dfs_prop.get("over_odds") is not None:
            _append_side_opportunity(
                opportunities,
                dfs_prop=dfs_prop,
                sharp_prop=sharp_prop,
                side="over",
                fair_prob=fair_over,
                breakeven_prob=breakeven_prob,
                fair_over=fair_over,
                fair_under=fair_under,
                dk_over_odds=dk_over,
                dk_under_odds=dk_under,
                min_ev=min_ev,
            )
        if dfs_prop.get("under_odds") is not None:
            _append_side_opportunity(
                opportunities,
                dfs_prop=dfs_prop,
                sharp_prop=sharp_prop,
                side="under",
                fair_prob=fair_under,
                breakeven_prob=breakeven_prob,
                fair_over=fair_over,
                fair_under=fair_under,
                dk_over_odds=dk_over,
                dk_under_odds=dk_under,
                min_ev=min_ev,
            )

    opportunities.sort(key=lambda row: row["ev"], reverse=True)
    return opportunities


def compare_betr_vs_draftkings(
    betr_props: list[dict],
    draftkings_props: list[dict],
    *,
    min_ev: float = 0.0,
    dfs_breakeven_odds: int = BETR_STANDARD_BREAKEVEN_ODDS,
) -> list[dict]:
    """Compare normalized Betr props against DraftKings and return ranked +EV plays."""
    return find_ev_opportunities(
        betr_props,
        draftkings_props,
        dfs_breakeven_odds=dfs_breakeven_odds,
        min_ev=min_ev,
    )
