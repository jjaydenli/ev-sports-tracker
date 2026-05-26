"""Cross-book EV comparison for Betr (DFS) vs DraftKings (sharp)."""

from __future__ import annotations

from core.flat_line import (
    adjusted_breakeven_probability,
    is_flat_line,
    line_kind,
)
from core.line_adjustment import (
    ResolvedSharpQuote,
    build_milestone_ladder,
    build_player_market_ladder,
    resolve_sharp_quote,
)
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


def build_player_market_key(prop: dict) -> str:
    """Player + market key (line-agnostic)."""
    return f"{normalize_player_name(prop['player'])}|{prop['market']}"


def index_props_by_key(props: list[dict]) -> dict[str, dict]:
    """Index props by matching key; first occurrence wins on duplicates."""
    indexed: dict[str, dict] = {}
    for prop in props:
        key = build_prop_key(prop)
        if key not in indexed:
            indexed[key] = prop
    return indexed


def _breakeven_probability(
    dfs_prop: dict,
    *,
    dfs_breakeven_odds: int,
    include_flat_lines: bool,
) -> float | None:
    """Implied breakeven for the DFS side; None when flat lines are skipped."""
    line = float(dfs_prop["line"])
    if is_flat_line(line) and not include_flat_lines:
        return None
    base = american_to_implied(dfs_breakeven_odds)
    if is_flat_line(line):
        return adjusted_breakeven_probability(base, dfs_prop["market"])
    return base


def _fair_probs_from_resolved(resolved: ResolvedSharpQuote) -> tuple[float, float]:
    """De-vig O/U quotes; milestone uses over implied only for under estimate."""
    if resolved.dk_line_kind == "milestone" or resolved.under_odds is None:
        fair_over = american_to_implied(resolved.over_odds)
        return fair_over, 1.0 - fair_over
    return multiplicative_devig(resolved.over_odds, resolved.under_odds)


def _favored_no_vig(fair_over: float, fair_under: float) -> tuple[str, float]:
    """Return the de-vig favored side and its fair probability."""
    if fair_over >= fair_under:
        return "over", fair_over
    return "under", fair_under


def _append_side_opportunity(
    opportunities: list[dict],
    *,
    dfs_prop: dict,
    resolved: ResolvedSharpQuote,
    side: str,
    fair_prob: float,
    breakeven_prob: float,
    fair_over: float,
    fair_under: float,
    min_ev: float,
) -> None:
    ev = calculate_ev(fair_prob, breakeven_prob)
    no_vig_side, no_vig_prob = _favored_no_vig(fair_over, fair_under)
    undisclosed_vig_caveat = resolved.dk_line_kind == "milestone"
    plus_ev = ev > min_ev

    opportunities.append(
        {
            "player": dfs_prop["player"],
            "market": dfs_prop["market"],
            "line": float(dfs_prop["line"]),
            "line_kind": dfs_prop.get("line_kind", line_kind(float(dfs_prop["line"]))),
            "side": side,
            "ev": round(ev, 4),
            "ev_pct": round(calculate_ev_percent(fair_prob, breakeven_prob), 2),
            "plus_ev": plus_ev,
            "no_vig_implied_pct": implied_prob_to_pct(no_vig_prob),
            "no_vig_favored_side": no_vig_side,
            "betr_implied_pct": implied_prob_to_pct(breakeven_prob),
            "dk_over_odds": resolved.over_odds,
            "dk_under_odds": resolved.under_odds,
            "betr_line": resolved.betr_line,
            "dk_matched_line": resolved.dk_line,
            "dk_main_line": resolved.dk_main_line,
            "line_source": resolved.adjustment_method,
            "corroborated": resolved.corroborated,
            "dk_line_kind": resolved.dk_line_kind,
            "dk_quote_one_sided": undisclosed_vig_caveat,
            "undisclosed_vig_caveat": undisclosed_vig_caveat,
            "plus_ev_milestone_caveat": undisclosed_vig_caveat and plus_ev,
            "dfs_sportsbook": dfs_prop.get("sportsbook", DEFAULT_DFS_SPORTSBOOK),
            "sharp_sportsbook": DEFAULT_SHARP_SPORTSBOOK,
        }
    )


def find_ev_opportunities(
    dfs_props: list[dict],
    sportsbook_props: list[dict],
    *,
    dfs_breakeven_odds: int = BETR_STANDARD_BREAKEVEN_ODDS,
    min_ev: float = 0.0,
    top_n: int | None = None,
    include_flat_lines: bool = False,
) -> list[dict]:
    """
    Match DFS props to sharp sportsbook lines and return ranked plays.

    Resolves DK main, alternate, interpolated, or extrapolated prices onto each
    Betr line before de-vig and EV calculation.
    """
    ou_ladder = build_player_market_ladder(
        sportsbook_props, normalize_player_name=normalize_player_name
    )
    milestone_ladder = build_milestone_ladder(
        sportsbook_props, normalize_player_name=normalize_player_name
    )
    opportunities: list[dict] = []

    for dfs_prop in dfs_props:
        breakeven_prob = _breakeven_probability(
            dfs_prop,
            dfs_breakeven_odds=dfs_breakeven_odds,
            include_flat_lines=include_flat_lines,
        )
        if breakeven_prob is None:
            continue

        resolved, _reason = resolve_sharp_quote(
            dfs_prop,
            ou_ladder,
            normalize_player_name=normalize_player_name,
            milestone_ladder=milestone_ladder,
        )
        if resolved is None:
            continue

        fair_over, fair_under = _fair_probs_from_resolved(resolved)

        if dfs_prop.get("over_odds") is not None:
            _append_side_opportunity(
                opportunities,
                dfs_prop=dfs_prop,
                resolved=resolved,
                side="over",
                fair_prob=fair_over,
                breakeven_prob=breakeven_prob,
                fair_over=fair_over,
                fair_under=fair_under,
                min_ev=min_ev,
            )
        if dfs_prop.get("under_odds") is not None:
            _append_side_opportunity(
                opportunities,
                dfs_prop=dfs_prop,
                resolved=resolved,
                side="under",
                fair_prob=fair_under,
                breakeven_prob=breakeven_prob,
                fair_over=fair_over,
                fair_under=fair_under,
                min_ev=min_ev,
            )

    opportunities.sort(key=lambda row: row["ev"], reverse=True)
    if top_n is not None:
        return opportunities[:top_n]
    return opportunities


def compare_betr_vs_draftkings(
    betr_props: list[dict],
    draftkings_props: list[dict],
    *,
    min_ev: float = 0.0,
    dfs_breakeven_odds: int = BETR_STANDARD_BREAKEVEN_ODDS,
    top_n: int | None = None,
    include_flat_lines: bool = False,
) -> list[dict]:
    """Compare normalized Betr props against DraftKings and return ranked plays."""
    return find_ev_opportunities(
        betr_props,
        draftkings_props,
        dfs_breakeven_odds=dfs_breakeven_odds,
        min_ev=min_ev,
        top_n=top_n,
        include_flat_lines=include_flat_lines,
    )


def _build_match_ladders(
    draftkings_props: list[dict],
) -> tuple[
    dict[str, dict[float, dict]],
    dict[str, dict[float, dict]],
]:
    ou_ladder = build_player_market_ladder(
        draftkings_props, normalize_player_name=normalize_player_name
    )
    milestone_ladder = build_milestone_ladder(
        draftkings_props, normalize_player_name=normalize_player_name
    )
    return ou_ladder, milestone_ladder


def betr_unmatched_reason(
    betr_prop: dict,
    ou_ladder: dict[str, dict[float, dict]],
    *,
    include_flat_lines: bool = False,
    milestone_ladder: dict[str, dict[float, dict]] | None = None,
) -> str | None:
    """Return None when the Betr prop can be aligned to DK; else a reason code."""
    line = float(betr_prop["line"])
    if is_flat_line(line) and not include_flat_lines:
        return "flat_line_skipped"

    _resolved, reason = resolve_sharp_quote(
        betr_prop,
        ou_ladder,
        normalize_player_name=normalize_player_name,
        milestone_ladder=milestone_ladder,
    )
    if _resolved is not None:
        return None
    return reason or "no_dk_market"


def betr_match_reason(
    betr_prop: dict,
    ou_ladder: dict[str, dict[float, dict]],
    *,
    include_flat_lines: bool = False,
    milestone_ladder: dict[str, dict[float, dict]] | None = None,
) -> str | None:
    """Backward-compatible alias for betr_unmatched_reason."""
    return betr_unmatched_reason(
        betr_prop,
        ou_ladder,
        include_flat_lines=include_flat_lines,
        milestone_ladder=milestone_ladder,
    )


def compute_match_stats(
    betr_props: list[dict],
    draftkings_props: list[dict],
    *,
    include_flat_lines: bool = False,
) -> dict[str, int | float]:
    """Count cross-book matches, unmatched props, and Betr match rate."""
    ou_ladder, milestone_ladder = _build_match_ladders(draftkings_props)
    betr_keys = {build_prop_key(prop) for prop in betr_props}

    matched = 0
    _REASON_COUNT_KEYS = {
        "no_dk_market": "unmatched_betr_no_dk_market",
        "line_mismatch": "unmatched_betr_line_mismatch",
        "no_dk_bracket_for_interp": "unmatched_betr_no_dk_bracket",
        "flat_line_skipped": "unmatched_betr_flat_line_skipped",
        "dk_missing_odds": "unmatched_betr_dk_missing_odds",
    }
    counts = {value: 0 for value in _REASON_COUNT_KEYS.values()}

    for betr_prop in betr_props:
        reason = betr_unmatched_reason(
            betr_prop,
            ou_ladder,
            include_flat_lines=include_flat_lines,
            milestone_ladder=milestone_ladder,
        )
        if reason is None:
            matched += 1
            continue
        count_key = _REASON_COUNT_KEYS.get(
            reason, "unmatched_betr_line_mismatch"
        )
        counts[count_key] += 1

    unmatched_betr = sum(counts.values())
    unmatched_dk = sum(
        1 for prop in draftkings_props if build_prop_key(prop) not in betr_keys
    )

    betr_total = len(betr_props)
    match_rate = round(100.0 * matched / betr_total, 1) if betr_total else 0.0

    return {
        "betr_props": betr_total,
        "dk_props": len(draftkings_props),
        "matched_keys": matched,
        "unmatched_betr": unmatched_betr,
        "unmatched_betr_no_dk_line": counts["unmatched_betr_no_dk_market"]
        + counts["unmatched_betr_line_mismatch"]
        + counts["unmatched_betr_no_dk_bracket"],
        "unmatched_betr_no_dk_market": counts["unmatched_betr_no_dk_market"],
        "unmatched_betr_line_mismatch": counts["unmatched_betr_line_mismatch"],
        "unmatched_betr_no_dk_bracket": counts["unmatched_betr_no_dk_bracket"],
        "unmatched_betr_flat_line_skipped": counts["unmatched_betr_flat_line_skipped"],
        "unmatched_betr_dk_missing_odds": counts["unmatched_betr_dk_missing_odds"],
        "unmatched_dk": unmatched_dk,
        "betr_match_rate_pct": match_rate,
    }


def list_unmatched_betr_props(
    betr_props: list[dict],
    draftkings_props: list[dict],
    *,
    include_flat_lines: bool = False,
) -> list[dict]:
    """Betr props that cannot be compared to DK, with reason and available DK lines."""
    ou_ladder, milestone_ladder = _build_match_ladders(draftkings_props)
    unmatched: list[dict] = []

    for betr_prop in betr_props:
        reason = betr_unmatched_reason(
            betr_prop,
            ou_ladder,
            include_flat_lines=include_flat_lines,
            milestone_ladder=milestone_ladder,
        )
        if reason is None:
            continue
        pm_key = build_player_market_key(betr_prop)
        dk_lines = sorted(
            set(ou_ladder.get(pm_key, {}).keys())
            | set(milestone_ladder.get(pm_key, {}).keys())
        )
        unmatched.append(
            {
                "player": betr_prop["player"],
                "market": betr_prop["market"],
                "line": float(betr_prop["line"]),
                "line_kind": betr_prop.get(
                    "line_kind", line_kind(float(betr_prop["line"]))
                ),
                "match_key": build_prop_key(betr_prop),
                "reason": reason,
                "dk_lines_available": dk_lines,
            }
        )

    return unmatched


def list_unmatched_dk_props(
    betr_props: list[dict],
    draftkings_props: list[dict],
) -> list[dict]:
    """DK props with no Betr line on the same player|market|line key."""
    betr_keys = {build_prop_key(prop) for prop in betr_props}
    unmatched: list[dict] = []

    for dk_prop in draftkings_props:
        key = build_prop_key(dk_prop)
        if key in betr_keys:
            continue
        unmatched.append(
            {
                "player": dk_prop["player"],
                "market": dk_prop["market"],
                "line": float(dk_prop["line"]),
                "match_key": key,
                "reason": "no_betr_line",
                "is_main_line": bool(dk_prop.get("is_main_line", True)),
            }
        )

    return unmatched
