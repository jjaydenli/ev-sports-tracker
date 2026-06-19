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
    build_milestone_ladders,
    build_player_market_ladder,
    is_ev_eligible_quote,
    merge_milestone_ladders,
    resolve_admitted_milestone_quote,
    resolve_multi_book_sharp_quote,
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


def _book_odds_from_resolved(
    resolved: ResolvedSharpQuote,
) -> tuple[int | None, int | None, int | None, int | None]:
    """Split DK vs FD O/U odds; avoid labeling FD-only quotes as DK."""
    books = tuple(resolved.sharp_books) if resolved.sharp_books else ("DraftKings",)
    dk_over = resolved.dk_over_odds
    dk_under = resolved.dk_under_odds
    fd_over = resolved.fd_over_odds
    fd_under = resolved.fd_under_odds
    if resolved.dk_line_kind == "milestone":
        if "DraftKings" not in books:
            dk_over = None
            dk_under = None
        if "FanDuel" not in books:
            fd_over = None
            fd_under = None
    elif dk_over is None and books == ("DraftKings",):
        dk_over = resolved.over_odds
        dk_under = resolved.under_odds
    elif fd_over is None and books == ("FanDuel",):
        fd_over = resolved.over_odds
        fd_under = resolved.under_odds
    return dk_over, dk_under, fd_over, fd_under


def normalize_player_name(name: str) -> str:
    """Normalize player names for cross-book matching."""
    return " ".join(name.strip().lower().split())


def build_prop_key(prop: dict) -> str:
    """Build a stable lookup key for cross-book matching."""
    player = normalize_player_name(prop["player"])
    market = prop["market"]
    line = prop["line"]
    key = f"{player}|{market}|{line}"
    league = prop.get("league")
    if league:
        key = f"{key}|{str(league).upper()}"
    return key


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
    if resolved.adjustment_method == "multi_book_consensus":
        fair_over = american_to_implied(resolved.over_odds)
        fair_under = american_to_implied(resolved.under_odds or 0)
        total = fair_over + fair_under
        if total > 0:
            return fair_over / total, fair_under / total
        return fair_over, fair_under
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
    dk_over, dk_under, fd_over, fd_under = _book_odds_from_resolved(resolved)

    opportunities.append(
        {
            "player": dfs_prop["player"],
            "league": dfs_prop.get("league", ""),
            "market": dfs_prop["market"],
            "line": float(dfs_prop["line"]),
            "line_kind": dfs_prop.get("line_kind", line_kind(float(dfs_prop["line"]))),
            "side": side,
            "ev": round(ev, 4),
            "ev_pct": round(calculate_ev_percent(fair_prob, breakeven_prob), 2),
            "plus_ev": plus_ev,
            "side_hit_pct": round(implied_prob_to_pct(fair_prob), 2),
            "no_vig_implied_pct": implied_prob_to_pct(no_vig_prob),
            "no_vig_favored_side": no_vig_side,
            "betr_implied_pct": implied_prob_to_pct(breakeven_prob),
            "dk_over_odds": dk_over,
            "dk_under_odds": dk_under,
            "fd_over_odds": fd_over,
            "fd_under_odds": fd_under,
            "sharp_books": list(resolved.sharp_books)
            if resolved.sharp_books
            else [DEFAULT_SHARP_SPORTSBOOK],
            "betr_line": resolved.betr_line,
            "dk_matched_line": resolved.dk_line,
            "dk_main_line": resolved.dk_main_line,
            "line_source": resolved.adjustment_method,
            "corroborated": resolved.corroborated,
            "dk_line_kind": resolved.dk_line_kind,
            "dk_quote_one_sided": undisclosed_vig_caveat,
            "undisclosed_vig_caveat": undisclosed_vig_caveat,
            "plus_ev_milestone_caveat": undisclosed_vig_caveat and plus_ev,
            "milestone_devig_method": resolved.milestone_devig_method,
            "milestone_admitted": resolved.milestone_admitted,
            "not_true_devig": resolved.dk_line_kind == "milestone",
            "dfs_sportsbook": dfs_prop.get("sportsbook", DEFAULT_DFS_SPORTSBOOK),
            "sharp_sportsbook": DEFAULT_SHARP_SPORTSBOOK,
            "is_live": dfs_prop.get("is_live", False),
        }
    )


def find_ev_opportunities(
    dfs_props: list[dict],
    sportsbook_props: list[dict],
    *,
    fanduel_props: list[dict] | None = None,
    dfs_breakeven_odds: int = BETR_STANDARD_BREAKEVEN_ODDS,
    min_ev: float = 0.0,
    top_n: int | None = None,
    include_flat_lines: bool = False,
    filter_min_ev: bool = False,
) -> list[dict]:
    """
    Match DFS props to sharp sportsbook lines and return ranked plays.

    Resolves DK (+ optional FanDuel) prices onto each Betr line before de-vig
    and EV calculation. Multi-book consensus uses equal-weight de-vig when both
    books have exact O/U at the Betr line.
    """
    ou_ladder = build_player_market_ladder(
        sportsbook_props, normalize_player_name=normalize_player_name
    )
    fd_ou_ladder = (
        build_player_market_ladder(
            fanduel_props, normalize_player_name=normalize_player_name
        )
        if fanduel_props
        else {}
    )
    sharp_milestone_props = [
        prop
        for prop in sportsbook_props
        if prop.get("line_kind") == "milestone"
    ]
    if fanduel_props:
        sharp_milestone_props.extend(
            prop
            for prop in fanduel_props
            if prop.get("line_kind") == "milestone"
        )
    milestone_ladders = build_milestone_ladders(
        sharp_milestone_props, normalize_player_name=normalize_player_name
    )
    milestone_ladder = merge_milestone_ladders(milestone_ladders)
    use_multi_book = bool(fanduel_props)
    ou_ladders: dict[str, dict[str, dict[float, dict]]] = {"DraftKings": ou_ladder}
    if fanduel_props:
        ou_ladders["FanDuel"] = fd_ou_ladder
    opportunities: list[dict] = []

    for dfs_prop in dfs_props:
        breakeven_prob = _breakeven_probability(
            dfs_prop,
            dfs_breakeven_odds=dfs_breakeven_odds,
            include_flat_lines=include_flat_lines,
        )
        if breakeven_prob is None:
            continue

        if use_multi_book:
            resolved, _reason = resolve_multi_book_sharp_quote(
                dfs_prop,
                ou_ladder,
                fd_ou_ladder,
                normalize_player_name=normalize_player_name,
                milestone_ladder=milestone_ladder,
            )
        else:
            resolved, _reason = resolve_sharp_quote(
                dfs_prop,
                ou_ladder,
                normalize_player_name=normalize_player_name,
                milestone_ladder=milestone_ladder,
                ou_ladders=ou_ladders,
            )
        if resolved is not None and is_ev_eligible_quote(resolved):
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

        # Admitted milestones from non-primary books (e.g. FD ms🔶 when DK O/U wins).
        for book in ("FanDuel",):
            book_milestone_ladder = milestone_ladders.get(book)
            if not book_milestone_ladder:
                continue
            if (
                resolved is not None
                and resolved.dk_line_kind == "milestone"
                and book in (resolved.sharp_books or ())
            ):
                continue
            milestone_resolved = resolve_admitted_milestone_quote(
                dfs_prop,
                book_milestone_ladder,
                normalize_player_name=normalize_player_name,
                ou_ladders=ou_ladders,
                hold_source_book_only=True,
            )
            if milestone_resolved is not None and dfs_prop.get("over_odds") is not None:
                ms_fair_over, ms_fair_under = _fair_probs_from_resolved(milestone_resolved)
                _append_side_opportunity(
                    opportunities,
                    dfs_prop=dfs_prop,
                    resolved=milestone_resolved,
                    side="over",
                    fair_prob=ms_fair_over,
                    breakeven_prob=breakeven_prob,
                    fair_over=ms_fair_over,
                    fair_under=ms_fair_under,
                    min_ev=min_ev,
                )

    opportunities.sort(key=lambda row: row["ev"], reverse=True)
    if filter_min_ev:
        opportunities = [row for row in opportunities if row["plus_ev"]]
    if top_n is not None:
        return opportunities[:top_n]
    return opportunities


def compare_betr_vs_draftkings(
    betr_props: list[dict],
    draftkings_props: list[dict],
    *,
    fanduel_props: list[dict] | None = None,
    min_ev: float = 0.0,
    dfs_breakeven_odds: int = BETR_STANDARD_BREAKEVEN_ODDS,
    top_n: int | None = None,
    include_flat_lines: bool = False,
    filter_min_ev: bool = False,
) -> list[dict]:
    """Compare normalized Betr props against sharp books and return ranked plays."""
    return find_ev_opportunities(
        betr_props,
        draftkings_props,
        fanduel_props=fanduel_props,
        dfs_breakeven_odds=dfs_breakeven_odds,
        min_ev=min_ev,
        top_n=top_n,
        include_flat_lines=include_flat_lines,
        filter_min_ev=filter_min_ev,
    )


def _build_match_ladders(
    draftkings_props: list[dict],
    fanduel_props: list[dict] | None = None,
) -> tuple[
    dict[str, dict[float, dict]],
    dict[str, dict[float, dict]],
    dict[str, dict[float, dict]] | None,
]:
    ou_ladder = build_player_market_ladder(
        draftkings_props, normalize_player_name=normalize_player_name
    )
    fd_ou_ladder = (
        build_player_market_ladder(
            fanduel_props, normalize_player_name=normalize_player_name
        )
        if fanduel_props
        else None
    )
    sharp_milestone_props = [
        prop
        for prop in draftkings_props
        if prop.get("line_kind") == "milestone"
    ]
    if fanduel_props:
        sharp_milestone_props.extend(
            prop
            for prop in fanduel_props
            if prop.get("line_kind") == "milestone"
        )
    milestone_ladder = merge_milestone_ladders(
        build_milestone_ladders(
            sharp_milestone_props, normalize_player_name=normalize_player_name
        )
    )
    return ou_ladder, milestone_ladder, fd_ou_ladder


def betr_unmatched_reason(
    betr_prop: dict,
    ou_ladder: dict[str, dict[float, dict]],
    *,
    include_flat_lines: bool = False,
    milestone_ladder: dict[str, dict[float, dict]] | None = None,
    fd_ou_ladder: dict[str, dict[float, dict]] | None = None,
) -> str | None:
    """Return None when the Betr prop can be aligned to sharp books; else a reason code."""
    line = float(betr_prop["line"])
    if is_flat_line(line) and not include_flat_lines:
        return "flat_line_skipped"

    if fd_ou_ladder is not None:
        resolved, reason = resolve_multi_book_sharp_quote(
            betr_prop,
            ou_ladder,
            fd_ou_ladder,
            normalize_player_name=normalize_player_name,
            milestone_ladder=milestone_ladder,
        )
    else:
        resolved, reason = resolve_sharp_quote(
            betr_prop,
            ou_ladder,
            normalize_player_name=normalize_player_name,
            milestone_ladder=milestone_ladder,
        )
    if resolved is None:
        return reason or "no_dk_market"
    if not is_ev_eligible_quote(resolved):
        return "no_exact_sharp_line"
    return None


def betr_match_reason(
    betr_prop: dict,
    ou_ladder: dict[str, dict[float, dict]],
    *,
    include_flat_lines: bool = False,
    milestone_ladder: dict[str, dict[float, dict]] | None = None,
    fd_ou_ladder: dict[str, dict[float, dict]] | None = None,
) -> str | None:
    """Backward-compatible alias for betr_unmatched_reason."""
    return betr_unmatched_reason(
        betr_prop,
        ou_ladder,
        include_flat_lines=include_flat_lines,
        milestone_ladder=milestone_ladder,
        fd_ou_ladder=fd_ou_ladder,
    )


def compute_match_stats(
    betr_props: list[dict],
    draftkings_props: list[dict],
    *,
    fanduel_props: list[dict] | None = None,
    include_flat_lines: bool = False,
) -> dict[str, int | float]:
    """Count cross-book matches, unmatched props, and Betr match rate."""
    ou_ladder, milestone_ladder, fd_ou_ladder = _build_match_ladders(
        draftkings_props, fanduel_props
    )
    betr_keys = {build_prop_key(prop) for prop in betr_props}

    matched = 0
    _REASON_COUNT_KEYS = {
        "no_dk_market": "unmatched_betr_no_dk_market",
        "no_exact_sharp_line": "unmatched_betr_no_exact_sharp_line",
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
            fd_ou_ladder=fd_ou_ladder,
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
        "fd_props": len(fanduel_props or []),
        "matched_keys": matched,
        "unmatched_betr": unmatched_betr,
        "unmatched_betr_no_dk_line": counts["unmatched_betr_no_dk_market"]
        + counts["unmatched_betr_no_exact_sharp_line"]
        + counts["unmatched_betr_line_mismatch"]
        + counts["unmatched_betr_no_dk_bracket"],
        "unmatched_betr_no_dk_market": counts["unmatched_betr_no_dk_market"],
        "unmatched_betr_no_exact_sharp_line": counts[
            "unmatched_betr_no_exact_sharp_line"
        ],
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
    fanduel_props: list[dict] | None = None,
    include_flat_lines: bool = False,
) -> list[dict]:
    """Betr props that cannot be compared to sharp books, with reason and available lines."""
    ou_ladder, milestone_ladder, fd_ou_ladder = _build_match_ladders(
        draftkings_props, fanduel_props
    )
    unmatched: list[dict] = []

    for betr_prop in betr_props:
        reason = betr_unmatched_reason(
            betr_prop,
            ou_ladder,
            include_flat_lines=include_flat_lines,
            milestone_ladder=milestone_ladder,
            fd_ou_ladder=fd_ou_ladder,
        )
        if reason is None:
            continue
        pm_key = build_player_market_key(betr_prop)
        dk_lines = sorted(
            set(ou_ladder.get(pm_key, {}).keys())
            | set(milestone_ladder.get(pm_key, {}).keys())
        )
        fd_lines = sorted(set((fd_ou_ladder or {}).get(pm_key, {}).keys()))
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
                "fd_lines_available": fd_lines,
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
