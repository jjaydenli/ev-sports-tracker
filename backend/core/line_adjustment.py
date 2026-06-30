"""Align Sportsbook prices to Betr lines via exact alt, interpolation, or extrapolation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from config.sharp_books import SHARP_BOOK_BY_NAME
from core.ladder_index import (
    _event_start_from_row,
    build_player_market_key,
)
from core.resolution_math import (
    _extrapolate_fair_probs,
    _extrapolate_milestone_fair_over,
    _fair_over_from_milestone,
    _fair_probs_from_odds,
    _interp_logit,
    _odds_from_fair_probs,
    devig_milestone_fair_over,
    estimate_ou_hold,
)

LineKind = Literal["ou", "milestone"]

# Sharp quotes eligible for +EV ranking.
EV_ELIGIBLE_ADJUSTMENT_METHODS: frozenset[str] = frozenset(
    {
        "exact",
        "dk_alt",
        "dk_interpolated",
        "fd_exact",
        "fd_alt",
        "espn_exact",
        "espn_alt",
        "multi_book_consensus",
    }
)

# True O/U at the Betr target line (not interpolated) — used for multi-book consensus.
EXACT_AT_TARGET_METHODS: frozenset[str] = frozenset(
    {"exact", "dk_alt", "fd_exact", "fd_alt", "espn_exact", "espn_alt"}
)


@dataclass(frozen=True)
class BookQuote:
    over_odds: int | None
    under_odds: int | None
    line_kind: LineKind
    line_source: str | None
    milestone_one_sided: bool = False


@dataclass(frozen=True)
class ResolvedSharpQuote:
    """Sharp-book prices aligned to the Betr target line."""

    over_odds: int
    under_odds: int | None
    dk_line: float
    betr_line: float
    adjustment_method: str
    corroborated: bool
    dk_main_line: float | None
    ev_line_kind: LineKind = "ou"
    per_book: tuple[tuple[str, BookQuote], ...] = ()
    sharp_books: tuple[str, ...] = ()
    milestone_admitted: bool = False
    milestone_devig_method: str | None = None
    sharp_by_book: tuple[tuple[str, str], ...] = ()
    sharp_event_start: str | None = None

    def book_quote(self, book: str) -> BookQuote | None:
        return next((bq for b, bq in self.per_book if b == book), None)


def is_ev_eligible_quote(quote: ResolvedSharpQuote) -> bool:
    """True when the sharp quote is eligible for +EV ranking."""
    if quote.ev_line_kind == "milestone":
        return (
            quote.adjustment_method == "dk_milestone_exact"
            and quote.milestone_admitted
        )
    return quote.adjustment_method in EV_ELIGIBLE_ADJUSTMENT_METHODS


def _exact_ou_method(book: str, is_alt: bool) -> str:
    if book == "DraftKings":
        return "dk_alt" if is_alt else "exact"
    prefix = {"FanDuel": "fd", "ESPN": "espn"}.get(book, book.lower())
    return f"{prefix}_alt" if is_alt else f"{prefix}_exact"


def _no_market_reason(book: str) -> str:
    return {
        "DraftKings": "no_dk_market",
        "FanDuel": "no_fd_market",
        "ESPN": "no_espn_market",
    }.get(book, f"no_{book.lower()}_market")


def _no_exact_line_reason(book: str) -> str:
    return {
        "FanDuel": "no_fd_exact_line",
        "ESPN": "no_espn_exact_line",
    }.get(book, f"no_{book.lower()}_exact_line")


def _resolve_ou_ladder(
    betr_prop: dict,
    ladder: dict[str, dict[float, dict[str, Any]]],
    *,
    normalize_player_name,
) -> tuple[ResolvedSharpQuote | None, str | None]:
    """Resolve using true O/U DK lines only."""
    market = betr_prop["market"]
    target_line = float(betr_prop["line"])
    pm_key = build_player_market_key(
        betr_prop, normalize_player_name=normalize_player_name
    )
    lines = ladder.get(pm_key)
    if not lines:
        return None, "no_dk_market"

    main_lines = sorted(
        line for line, row in lines.items() if row.get("is_main_line", True)
    )
    dk_main_line = main_lines[0] if main_lines else None

    if target_line in lines:
        row = lines[target_line]
        method = "dk_alt" if not row.get("is_main_line", True) else "exact"
        bq = BookQuote(
            over_odds=row["over_odds"],
            under_odds=row["under_odds"],
            line_kind="ou",
            line_source=method,
        )
        return (
            ResolvedSharpQuote(
                over_odds=row["over_odds"],
                under_odds=row["under_odds"],
                dk_line=target_line,
                betr_line=target_line,
                adjustment_method=method,
                corroborated=True,
                dk_main_line=dk_main_line,
                ev_line_kind="ou",
                per_book=(("DraftKings", bq),),
                sharp_books=("DraftKings",),
                sharp_event_start=_event_start_from_row(row),
            ),
            None,
        )

    sorted_lines = sorted(lines.keys())
    lower = [line for line in sorted_lines if line < target_line]
    upper = [line for line in sorted_lines if line > target_line]

    if lower and upper:
        line_low = lower[-1]
        line_high = upper[0]
        row_low = lines[line_low]
        row_high = lines[line_high]
        fair_low_over, fair_low_under = _fair_probs_from_odds(
            row_low["over_odds"], row_low["under_odds"]
        )
        fair_high_over, fair_high_under = _fair_probs_from_odds(
            row_high["over_odds"], row_high["under_odds"]
        )
        weight_high = (target_line - line_low) / (line_high - line_low)
        fair_over = _interp_logit(fair_low_over, fair_high_over, weight_high)
        fair_under = _interp_logit(fair_low_under, fair_high_under, weight_high)
        over_odds, under_odds = _odds_from_fair_probs(fair_over, fair_under)
        bq = BookQuote(
            over_odds=over_odds,
            under_odds=under_odds,
            line_kind="ou",
            line_source="dk_interpolated",
        )
        return (
            ResolvedSharpQuote(
                over_odds=over_odds,
                under_odds=under_odds,
                dk_line=target_line,
                betr_line=target_line,
                adjustment_method="dk_interpolated",
                corroborated=True,
                dk_main_line=dk_main_line,
                ev_line_kind="ou",
                per_book=(("DraftKings", bq),),
                sharp_books=("DraftKings",),
                sharp_event_start=_event_start_from_row(row_low),
            ),
            None,
        )

    anchor_line = dk_main_line if dk_main_line is not None else sorted_lines[0]
    anchor = lines[anchor_line]
    fair_over, fair_under = _fair_probs_from_odds(
        anchor["over_odds"], anchor["under_odds"]
    )
    fair_over, fair_under = _extrapolate_fair_probs(
        fair_over,
        fair_under,
        anchor_line=anchor_line,
        target_line=target_line,
        market=market,
    )
    over_odds, under_odds = _odds_from_fair_probs(fair_over, fair_under)
    bq = BookQuote(
        over_odds=over_odds,
        under_odds=under_odds,
        line_kind="ou",
        line_source="dk_extrapolated",
    )
    return (
        ResolvedSharpQuote(
            over_odds=over_odds,
            under_odds=under_odds,
            dk_line=anchor_line,
            betr_line=target_line,
            adjustment_method="dk_extrapolated",
            corroborated=False,
            dk_main_line=dk_main_line,
            ev_line_kind="ou",
            per_book=(("DraftKings", bq),),
            sharp_books=("DraftKings",),
            sharp_event_start=_event_start_from_row(anchor),
        ),
        None,
    )


def _resolve_milestone_ladder(
    betr_prop: dict,
    ladder: dict[str, dict[float, dict[str, Any]]],
    *,
    normalize_player_name,
    ou_ladders: dict[str, dict[str, dict[float, dict[str, Any]]]] | None = None,
    hold_source_book_only: bool = False,
) -> tuple[ResolvedSharpQuote | None, str | None]:
    """Resolve using milestone (N+) over-only lines."""
    from config.settings import MILESTONE_MIN_FAIR_OVER

    market = betr_prop["market"]
    target_line = float(betr_prop["line"])
    pm_key = build_player_market_key(
        betr_prop, normalize_player_name=normalize_player_name
    )
    lines = ladder.get(pm_key)
    if not lines:
        return None, "no_dk_market"

    main_lines = sorted(
        line for line, row in lines.items() if row.get("is_main_line", True)
    )
    dk_main_line = main_lines[0] if main_lines else None

    if target_line in lines:
        row = lines[target_line]
        source_book = row.get("sportsbook", "DraftKings")
        preferred_hold = (
            estimate_ou_hold(
                ou_ladders or {},
                pm_key,
                preferred_book=source_book,
                source_book_only=hold_source_book_only,
            )
            if ou_ladders
            else None
        )
        fair_over, devig_method = devig_milestone_fair_over(
            lines,
            target_line,
            market=market,
            ou_hold=preferred_hold,
        )
        devigged_over, devigged_under = _odds_from_fair_probs(fair_over, 1.0 - fair_over)
        admitted_over = fair_over >= MILESTONE_MIN_FAIR_OVER
        admitted_under = fair_over < 0.5  # under is heavy side; Betr under can be +EV
        admitted = admitted_over or admitted_under
        raw_over = int(row["over_odds"])
        bq = BookQuote(
            over_odds=raw_over,
            under_odds=None,
            line_kind="milestone",
            line_source="dk_milestone_exact",
            milestone_one_sided=True,
        )
        return (
            ResolvedSharpQuote(
                over_odds=devigged_over,
                under_odds=devigged_under if admitted_under else None,
                dk_line=target_line,
                betr_line=target_line,
                adjustment_method="dk_milestone_exact",
                corroborated=False,
                dk_main_line=dk_main_line,
                ev_line_kind="milestone",
                per_book=((source_book, bq),),
                sharp_books=(source_book,),
                milestone_admitted=admitted,
                milestone_devig_method=devig_method,
                sharp_event_start=_event_start_from_row(row),
            ),
            None,
        )

    sorted_lines = sorted(lines.keys())
    lower = [line for line in sorted_lines if line < target_line]
    upper = [line for line in sorted_lines if line > target_line]

    if lower and upper:
        line_low = lower[-1]
        line_high = upper[0]
        fair_low = _fair_over_from_milestone(lines[line_low]["over_odds"])
        fair_high = _fair_over_from_milestone(lines[line_high]["over_odds"])
        weight_high = (target_line - line_low) / (line_high - line_low)
        fair_over = _interp_logit(fair_low, fair_high, weight_high)
        over_odds, _ = _odds_from_fair_probs(fair_over, 1 - fair_over)
        ms_book = lines[line_low].get("sportsbook", "DraftKings")
        bq = BookQuote(
            over_odds=over_odds,
            under_odds=None,
            line_kind="milestone",
            line_source="dk_milestone_interpolated",
            milestone_one_sided=True,
        )
        return (
            ResolvedSharpQuote(
                over_odds=over_odds,
                under_odds=None,
                dk_line=target_line,
                betr_line=target_line,
                adjustment_method="dk_milestone_interpolated",
                corroborated=False,
                dk_main_line=dk_main_line,
                ev_line_kind="milestone",
                per_book=((ms_book, bq),),
                sharp_books=(ms_book,),
                sharp_event_start=_event_start_from_row(lines[line_low]),
            ),
            None,
        )

    anchor_line = dk_main_line if dk_main_line is not None else sorted_lines[0]
    anchor = lines[anchor_line]
    fair_over = _extrapolate_milestone_fair_over(
        _fair_over_from_milestone(anchor["over_odds"]),
        anchor_line=anchor_line,
        target_line=target_line,
        market=market,
    )
    over_odds, _ = _odds_from_fair_probs(fair_over, 1 - fair_over)
    ms_book = anchor.get("sportsbook", "DraftKings")
    bq = BookQuote(
        over_odds=over_odds,
        under_odds=None,
        line_kind="milestone",
        line_source="dk_milestone_extrapolated",
        milestone_one_sided=True,
    )
    return (
        ResolvedSharpQuote(
            over_odds=over_odds,
            under_odds=None,
            dk_line=anchor_line,
            betr_line=target_line,
            adjustment_method="dk_milestone_extrapolated",
            corroborated=False,
            dk_main_line=dk_main_line,
            ev_line_kind="milestone",
            per_book=((ms_book, bq),),
            sharp_books=(ms_book,),
            sharp_event_start=_event_start_from_row(anchor),
        ),
        None,
    )


def resolve_admitted_milestone_quote(
    betr_prop: dict,
    milestone_ladder: dict[str, dict[float, dict[str, Any]]],
    *,
    normalize_player_name,
    ou_ladders: dict[str, dict[str, dict[float, dict[str, Any]]]] | None = None,
    hold_source_book_only: bool = False,
) -> ResolvedSharpQuote | None:
    """Return an exact, gate-admitted milestone quote, or None."""
    quote, _ = _resolve_milestone_ladder(
        betr_prop,
        milestone_ladder,
        normalize_player_name=normalize_player_name,
        ou_ladders=ou_ladders,
        hold_source_book_only=hold_source_book_only,
    )
    if quote is None or not is_ev_eligible_quote(quote):
        return None
    return quote


def resolve_sharp_quote(
    betr_prop: dict,
    ou_ladder: dict[str, dict[float, dict[str, Any]]],
    *,
    normalize_player_name,
    milestone_ladder: dict[str, dict[float, dict[str, Any]]] | None = None,
    ou_ladders: dict[str, dict[str, dict[float, dict[str, Any]]]] | None = None,
) -> tuple[ResolvedSharpQuote | None, str | None]:
    """
    Resolve DK prices for a Betr prop.

    Prefers true O/U lines; falls back to milestone (N+) when O/U is missing
    or only extrapolated from a single O/U anchor.
    """
    ou_quote, ou_reason = _resolve_ou_ladder(
        betr_prop, ou_ladder, normalize_player_name=normalize_player_name
    )

    use_milestone = milestone_ladder and (
        ou_quote is None
        or ou_quote.adjustment_method == "dk_extrapolated"
    )
    if use_milestone:
        milestone_ou_ladders = ou_ladders or {"DraftKings": ou_ladder}
        milestone_quote, milestone_reason = _resolve_milestone_ladder(
            betr_prop,
            milestone_ladder,
            normalize_player_name=normalize_player_name,
            ou_ladders=milestone_ou_ladders,
        )
        if milestone_quote is not None:
            return milestone_quote, None
        if ou_quote is None:
            return None, milestone_reason or ou_reason

    if ou_quote is not None:
        return ou_quote, None
    return None, ou_reason or "no_dk_market"


def _resolve_exact_ou(
    betr_prop: dict,
    ou_ladder: dict[str, dict[float, dict[str, Any]]],
    *,
    book: str,
    normalize_player_name,
) -> tuple[ResolvedSharpQuote | None, str | None]:
    """Resolve O/U only when an exact alt or main line exists at the Betr line."""
    target_line = float(betr_prop["line"])
    pm_key = build_player_market_key(
        betr_prop, normalize_player_name=normalize_player_name
    )
    lines = ou_ladder.get(pm_key)
    if not lines:
        return None, _no_market_reason(book)
    if target_line not in lines:
        return None, _no_exact_line_reason(book)

    row = lines[target_line]
    main_lines = sorted(
        line for line, entry in lines.items() if entry.get("is_main_line", True)
    )
    main_line = main_lines[0] if main_lines else None
    method = _exact_ou_method(book, not row.get("is_main_line", True))
    bq = BookQuote(
        over_odds=row["over_odds"],
        under_odds=row["under_odds"],
        line_kind="ou",
        line_source=method,
    )
    return (
        ResolvedSharpQuote(
            over_odds=row["over_odds"],
            under_odds=row["under_odds"],
            dk_line=target_line,
            betr_line=target_line,
            adjustment_method=method,
            corroborated=True,
            dk_main_line=main_line,
            ev_line_kind="ou",
            per_book=((book, bq),),
            sharp_books=(book,),
            sharp_event_start=_event_start_from_row(row),
        ),
        None,
    )


def resolve_book_sharp_quote(
    book: str,
    betr_prop: dict,
    ou_ladder: dict[str, dict[float, dict[str, Any]]],
    milestone_ladder: dict[str, dict[float, dict[str, Any]]] | None,
    *,
    normalize_player_name,
    ou_ladders: dict[str, dict[str, dict[float, dict[str, Any]]]] | None = None,
) -> tuple[ResolvedSharpQuote | None, str | None]:
    """Resolve one sharp book: O/U first, milestone when O/U missing or extrapolated only."""
    cfg = SHARP_BOOK_BY_NAME.get(book)
    if cfg is None:
        return None, f"unknown_book_{book}"

    if cfg.ou_resolution == "full":
        ou_quote, ou_reason = _resolve_ou_ladder(
            betr_prop, ou_ladder, normalize_player_name=normalize_player_name
        )
    else:
        ou_quote, ou_reason = _resolve_exact_ou(
            betr_prop,
            ou_ladder,
            book=book,
            normalize_player_name=normalize_player_name,
        )

    use_milestone = cfg.milestone_fallback and milestone_ladder and (
        ou_quote is None
        or (cfg.ou_resolution == "full" and ou_quote.adjustment_method == "dk_extrapolated")
    )
    if use_milestone:
        milestone_ou_ladders = ou_ladders or {book: ou_ladder}
        hold_for_milestone = (
            cfg.hold_own_book_only
            if cfg.hold_own_book_only
            else book in (ou_ladders or {})
        )
        milestone_quote, milestone_reason = _resolve_milestone_ladder(
            betr_prop,
            milestone_ladder,
            normalize_player_name=normalize_player_name,
            ou_ladders=milestone_ou_ladders,
            hold_source_book_only=hold_for_milestone,
        )
        if milestone_quote is not None:
            return milestone_quote, None
        if ou_quote is None:
            return None, milestone_reason or ou_reason
    if ou_quote is not None:
        return ou_quote, None
    return None, ou_reason or _no_market_reason(book)
