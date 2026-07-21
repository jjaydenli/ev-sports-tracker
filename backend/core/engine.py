"""Cross-book EV comparison for Betr (DFS) vs DraftKings (sharp)."""

from __future__ import annotations

from dataclasses import dataclass

from config.market_maps import O05_EQUIVALENT_MARKETS
from core.flat_line import (
    adjusted_breakeven_probability,
    is_flat_line,
    line_kind,
)
from core.ladder_index import (
    build_match_context_key,
    build_milestone_ladders,
    build_player_market_ladder,
    merge_milestone_ladders,
)
from core.ladder_index import (
    build_player_market_key as build_scoped_player_market_key,
)
from core.line_adjustment import (
    ResolvedSharpQuote,
    is_ev_eligible_quote,
    resolve_sharp_quote,
)
from core.multi_book_resolver import resolve_multi_book_sharp_quote
from utils.math_utils import (
    BETR_STANDARD_BREAKEVEN_ODDS,
    american_to_implied,
    calculate_ev,
    calculate_ev_percent,
    implied_prob_to_pct,
    multiplicative_devig,
)

DEFAULT_SHARP_SPORTSBOOK = "DraftKings"


@dataclass(frozen=True)
class DFSSide:
    name: str
    breakeven_odds: int


BETR = DFSSide(name="Betr", breakeven_odds=BETR_STANDARD_BREAKEVEN_ODDS)


def _book_field(book: str, field: str, resolved: ResolvedSharpQuote):
    bq = resolved.book_quote(book)
    if bq is None:
        return "ou" if field == "line_kind" else (False if field == "milestone_one_sided" else None)
    if field == "line_kind":
        return bq.line_kind
    if field == "milestone_one_sided":
        return bq.milestone_one_sided
    if field == "line_source":
        return bq.line_source
    if field == "over_odds":
        return bq.over_odds
    if field == "under_odds":
        return bq.under_odds
    raise ValueError(f"unknown book field: {field}")


def _book_odds_from_resolved(
    resolved: ResolvedSharpQuote,
) -> tuple[int | None, int | None, int | None, int | None, int | None, int | None]:
    """Split DK vs FD vs ESPN O/U odds from per_book; preserve output schema."""
    books = tuple(resolved.sharp_books) if resolved.sharp_books else ("DraftKings",)
    dk_over = _book_field("DraftKings", "over_odds", resolved)
    dk_under = _book_field("DraftKings", "under_odds", resolved)
    fd_over = _book_field("FanDuel", "over_odds", resolved)
    fd_under = _book_field("FanDuel", "under_odds", resolved)
    espn_over = _book_field("ESPN", "over_odds", resolved)
    espn_under = _book_field("ESPN", "under_odds", resolved)

    if dk_over is None and books == ("DraftKings",):
        dk_over = resolved.over_odds
        dk_under = resolved.under_odds
    elif fd_over is None and books == ("FanDuel",):
        fd_over = resolved.over_odds
        fd_under = resolved.under_odds
    elif espn_over is None and books == ("ESPN",):
        espn_over = resolved.over_odds
        espn_under = resolved.under_odds
    return dk_over, dk_under, fd_over, fd_under, espn_over, espn_under


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
    """Player + market key (line-agnostic), with optional game/live scope."""
    return build_scoped_player_market_key(
        prop, normalize_player_name=normalize_player_name
    )


def _filter_sharp_props_by_match_context(
    betr_prop: dict,
    props: list[dict],
) -> list[dict]:
    """Keep sharp rows sharing the same canonical match context as the Betr prop."""
    betr_key = build_match_context_key(
        betr_prop, normalize_player_name=normalize_player_name
    )
    native = [
        prop
        for prop in props
        if build_match_context_key(prop, normalize_player_name=normalize_player_name)
        == betr_key
    ]

    betr_market = betr_prop["market"]
    if betr_market not in O05_EQUIVALENT_MARKETS or float(betr_prop["line"]) != 0.5:
        return native

    has_native_05 = any(float(prop["line"]) == 0.5 for prop in native)
    if has_native_05:
        return native

    borrowed: list[dict] = []
    for prop in props:
        if (
            prop.get("market") in O05_EQUIVALENT_MARKETS
            and prop.get("market") != betr_market
            and float(prop.get("line", -1)) == 0.5
        ):
            swapped = {**prop, "market": betr_market}
            if (
                build_match_context_key(
                    swapped, normalize_player_name=normalize_player_name
                )
                == betr_key
            ):
                borrowed.append(swapped)
    return native + borrowed


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
    if resolved.ev_line_kind == "milestone" or resolved.under_odds is None:
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
    dfs_sportsbook: str,
) -> None:
    ev = calculate_ev(fair_prob, breakeven_prob)
    no_vig_side, no_vig_prob = _favored_no_vig(fair_over, fair_under)
    ev_from_milestone = resolved.adjustment_method == "milestone_exact"
    undisclosed_vig_caveat = ev_from_milestone
    plus_ev = ev > 0
    dk_over, dk_under, fd_over, fd_under, espn_over, espn_under = (
        _book_odds_from_resolved(resolved)
    )
    sharp_by_book = (
        dict(resolved.sharp_by_book) if resolved.sharp_by_book else None
    )

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
            "espn_over_odds": espn_over,
            "espn_under_odds": espn_under,
            "sharp_books": list(resolved.sharp_books)
            if resolved.sharp_books
            else [DEFAULT_SHARP_SPORTSBOOK],
            "betr_line": resolved.betr_line,
            "dk_matched_line": resolved.dk_line,
            "dk_main_line": resolved.dk_main_line,
            "line_source": resolved.adjustment_method,
            "corroborated": resolved.corroborated,
            "dk_line_kind": _book_field("DraftKings", "line_kind", resolved),
            "fd_line_kind": _book_field("FanDuel", "line_kind", resolved),
            "espn_line_kind": _book_field("ESPN", "line_kind", resolved),
            "dk_milestone_one_sided": _book_field(
                "DraftKings", "milestone_one_sided", resolved
            ),
            "fd_milestone_one_sided": _book_field(
                "FanDuel", "milestone_one_sided", resolved
            ),
            "espn_milestone_one_sided": _book_field(
                "ESPN", "milestone_one_sided", resolved
            ),
            "dk_line_source": _book_field("DraftKings", "line_source", resolved),
            "fd_line_source": _book_field("FanDuel", "line_source", resolved),
            "espn_line_source": _book_field("ESPN", "line_source", resolved),
            "sharp_by_book": sharp_by_book,
            "dk_quote_one_sided": undisclosed_vig_caveat,
            "undisclosed_vig_caveat": undisclosed_vig_caveat,
            "plus_ev_milestone_caveat": undisclosed_vig_caveat and plus_ev,
            "milestone_devig_method": resolved.milestone_devig_method,
            "milestone_admitted": resolved.milestone_admitted,
            "not_true_devig": ev_from_milestone,
            "dfs_sportsbook": dfs_sportsbook,
            "sharp_sportsbook": DEFAULT_SHARP_SPORTSBOOK,
            "is_live": dfs_prop.get("is_live", False),
            "game": dfs_prop.get("game"),
            "team": dfs_prop.get("team"),
        }
    )


def find_ev_opportunities(
    dfs_props: list[dict],
    sportsbook_props: list[dict],
    *,
    fanduel_props: list[dict] | None = None,
    espn_props: list[dict] | None = None,
    dfs_side: DFSSide = BETR,
    dfs_breakeven_odds: int | None = None,
    min_ev: float | None = None,
    top_n: int | None = None,
    include_flat_lines: bool = False,
) -> list[dict]:
    """
    Match DFS props to sharp sportsbook lines and return ranked plays.

    Resolves DK (+ optional FanDuel) prices onto each Betr line before de-vig
    and EV calculation. Multi-book consensus uses equal-weight de-vig when both
    books have exact O/U at the Betr line.
    """
    ou_ladders: dict[str, dict[str, dict[float, dict]]] = {"DraftKings": {}}
    opportunities: list[dict] = []
    effective_breakeven_odds = (
        dfs_breakeven_odds
        if dfs_breakeven_odds is not None
        else dfs_side.breakeven_odds
    )

    for dfs_prop in dfs_props:
        if not dfs_prop.get("is_live") and not dfs_prop.get("event_start"):
            continue

        breakeven_prob = _breakeven_probability(
            dfs_prop,
            dfs_breakeven_odds=effective_breakeven_odds,
            include_flat_lines=include_flat_lines,
        )
        if breakeven_prob is None:
            continue

        filtered_dk = _filter_sharp_props_by_match_context(
            dfs_prop, sportsbook_props
        )
        filtered_fd = (
            _filter_sharp_props_by_match_context(dfs_prop, fanduel_props)
            if fanduel_props
            else []
        )
        filtered_espn = (
            _filter_sharp_props_by_match_context(dfs_prop, espn_props)
            if espn_props
            else []
        )
        if not filtered_dk and not filtered_fd and not filtered_espn:
            continue

        ou_ladder = build_player_market_ladder(
            filtered_dk, normalize_player_name=normalize_player_name
        )
        fd_ou_ladder = (
            build_player_market_ladder(
                filtered_fd, normalize_player_name=normalize_player_name
            )
            if fanduel_props
            else {}
        )
        espn_ou_ladder = (
            build_player_market_ladder(
                filtered_espn, normalize_player_name=normalize_player_name
            )
            if espn_props
            else None
        )
        sharp_milestone_props = [
            prop
            for prop in filtered_dk
            if prop.get("line_kind") == "milestone"
        ]
        if fanduel_props:
            sharp_milestone_props.extend(
                prop
                for prop in filtered_fd
                if prop.get("line_kind") == "milestone"
            )
        if espn_props:
            sharp_milestone_props.extend(
                prop
                for prop in filtered_espn
                if prop.get("line_kind") == "milestone"
            )
        milestone_ladders = build_milestone_ladders(
            sharp_milestone_props, normalize_player_name=normalize_player_name
        )
        milestone_ladder = merge_milestone_ladders(milestone_ladders)
        use_multi_book = bool(fanduel_props or espn_props)
        ou_ladders["DraftKings"] = ou_ladder
        if fanduel_props:
            ou_ladders["FanDuel"] = fd_ou_ladder
        if espn_props and espn_ou_ladder is not None:
            ou_ladders["ESPN"] = espn_ou_ladder

        if use_multi_book:
            resolved, _reason = resolve_multi_book_sharp_quote(
                dfs_prop,
                ou_ladder,
                fd_ou_ladder,
                normalize_player_name=normalize_player_name,
                milestone_ladder=milestone_ladder,
                dk_milestone_ladder=milestone_ladders.get("DraftKings"),
                fd_milestone_ladder=milestone_ladders.get("FanDuel"),
                espn_ou_ladder=espn_ou_ladder,
                espn_milestone_ladder=milestone_ladders.get("ESPN"),
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
                    dfs_sportsbook=dfs_side.name,
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
                    dfs_sportsbook=dfs_side.name,
                )

    opportunities.sort(key=lambda row: row["ev"], reverse=True)
    if min_ev is not None:
        opportunities = [row for row in opportunities if row["ev"] >= min_ev]
    if top_n is not None:
        return opportunities[:top_n]
    return opportunities


def compare_betr_vs_draftkings(
    betr_props: list[dict],
    draftkings_props: list[dict],
    *,
    fanduel_props: list[dict] | None = None,
    espn_props: list[dict] | None = None,
    dfs_side: DFSSide = BETR,
    min_ev: float | None = None,
    dfs_breakeven_odds: int | None = None,
    top_n: int | None = None,
    include_flat_lines: bool = False,
) -> list[dict]:
    """Compare normalized Betr props against sharp books and return ranked plays."""
    return find_ev_opportunities(
        betr_props,
        draftkings_props,
        fanduel_props=fanduel_props,
        espn_props=espn_props,
        dfs_side=dfs_side,
        dfs_breakeven_odds=dfs_breakeven_odds,
        min_ev=min_ev,
        top_n=top_n,
        include_flat_lines=include_flat_lines,
    )


def _build_match_ladders(
    draftkings_props: list[dict],
    fanduel_props: list[dict] | None = None,
    espn_props: list[dict] | None = None,
) -> tuple[
    dict[str, dict[float, dict]],
    dict[str, dict[float, dict]],
    dict[str, dict[float, dict]] | None,
    dict[str, dict[float, dict]] | None,
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
    espn_ou_ladder = (
        build_player_market_ladder(
            espn_props, normalize_player_name=normalize_player_name
        )
        if espn_props
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
    if espn_props:
        sharp_milestone_props.extend(
            prop
            for prop in espn_props
            if prop.get("line_kind") == "milestone"
        )
    all_milestone_ladders = build_milestone_ladders(
        sharp_milestone_props, normalize_player_name=normalize_player_name
    )
    espn_milestone_ladder = all_milestone_ladders.get("ESPN") or None
    milestone_ladder = merge_milestone_ladders(all_milestone_ladders)
    return ou_ladder, milestone_ladder, fd_ou_ladder, espn_ou_ladder, espn_milestone_ladder


def betr_unmatched_reason(
    betr_prop: dict,
    ou_ladder: dict[str, dict[float, dict]],
    *,
    include_flat_lines: bool = False,
    milestone_ladder: dict[str, dict[float, dict]] | None = None,
    fd_ou_ladder: dict[str, dict[float, dict]] | None = None,
    espn_ou_ladder: dict[str, dict[float, dict]] | None = None,
    espn_milestone_ladder: dict[str, dict[float, dict]] | None = None,
) -> str | None:
    """Return None when the Betr prop can be aligned to sharp books; else a reason code."""
    line = float(betr_prop["line"])
    if is_flat_line(line) and not include_flat_lines:
        return "flat_line_skipped"

    if fd_ou_ladder is not None or espn_ou_ladder is not None or espn_milestone_ladder:
        resolved, reason = resolve_multi_book_sharp_quote(
            betr_prop,
            ou_ladder,
            fd_ou_ladder or {},
            normalize_player_name=normalize_player_name,
            milestone_ladder=milestone_ladder,
            espn_ou_ladder=espn_ou_ladder,
            espn_milestone_ladder=espn_milestone_ladder,
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
    espn_ou_ladder: dict[str, dict[float, dict]] | None = None,
    espn_milestone_ladder: dict[str, dict[float, dict]] | None = None,
) -> str | None:
    """Backward-compatible alias for betr_unmatched_reason."""
    return betr_unmatched_reason(
        betr_prop,
        ou_ladder,
        include_flat_lines=include_flat_lines,
        milestone_ladder=milestone_ladder,
        fd_ou_ladder=fd_ou_ladder,
        espn_ou_ladder=espn_ou_ladder,
        espn_milestone_ladder=espn_milestone_ladder,
    )


def compute_match_stats(
    betr_props: list[dict],
    draftkings_props: list[dict],
    *,
    fanduel_props: list[dict] | None = None,
    espn_props: list[dict] | None = None,
    include_flat_lines: bool = False,
) -> dict[str, int | float]:
    """Count cross-book matches, unmatched props, and Betr match rate."""
    ou_ladder, milestone_ladder, fd_ou_ladder, espn_ou_ladder, espn_milestone_ladder = _build_match_ladders(
        draftkings_props, fanduel_props, espn_props
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
    counts = dict.fromkeys(_REASON_COUNT_KEYS.values(), 0)

    for betr_prop in betr_props:
        reason = betr_unmatched_reason(
            betr_prop,
            ou_ladder,
            include_flat_lines=include_flat_lines,
            milestone_ladder=milestone_ladder,
            fd_ou_ladder=fd_ou_ladder,
            espn_ou_ladder=espn_ou_ladder,
            espn_milestone_ladder=espn_milestone_ladder,
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
        "espn_props": len(espn_props or []),
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
    espn_props: list[dict] | None = None,
    include_flat_lines: bool = False,
) -> list[dict]:
    """Betr props that cannot be compared to sharp books, with reason and available lines."""
    ou_ladder, milestone_ladder, fd_ou_ladder, espn_ou_ladder, espn_milestone_ladder = _build_match_ladders(
        draftkings_props, fanduel_props, espn_props
    )
    unmatched: list[dict] = []

    for betr_prop in betr_props:
        reason = betr_unmatched_reason(
            betr_prop,
            ou_ladder,
            include_flat_lines=include_flat_lines,
            milestone_ladder=milestone_ladder,
            fd_ou_ladder=fd_ou_ladder,
            espn_ou_ladder=espn_ou_ladder,
            espn_milestone_ladder=espn_milestone_ladder,
        )
        if reason is None:
            continue
        pm_key = build_player_market_key(betr_prop)
        dk_lines = sorted(
            set(ou_ladder.get(pm_key, {}).keys())
            | set(milestone_ladder.get(pm_key, {}).keys())
        )
        fd_lines = sorted(set((fd_ou_ladder or {}).get(pm_key, {}).keys()))
        espn_lines = sorted(set((espn_ou_ladder or {}).get(pm_key, {}).keys()))
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
                "espn_lines_available": espn_lines,
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
