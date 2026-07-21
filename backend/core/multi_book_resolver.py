"""Multi-book sharp quote assembly and consensus."""

from __future__ import annotations

from typing import Any

from config.sharp_books import SHARP_BOOKS
from core.line_adjustment import (
    EV_ELIGIBLE_ADJUSTMENT_METHODS,
    EXACT_AT_TARGET_METHODS,
    BookQuote,
    ResolvedSharpQuote,
    is_ev_eligible_quote,
    resolve_book_sharp_quote,
)
from core.resolution_math import _fair_probs_from_odds, _odds_from_fair_probs


def load_sharp_book_weights() -> dict[str, float]:
    """
    Per-book weights for multi-book consensus (env-tunable; equal 1.0 defaults).

    When adding a third sharp book, extend this dict and each book's eligibility
    rules (FD: exact O/U only; DK: O/U ladder + milestone fallback; etc.).
    """
    from config.settings import (
        SHARP_BOOK_WEIGHTS_DK,
        SHARP_BOOK_WEIGHTS_ESPN,
        SHARP_BOOK_WEIGHTS_FD,
    )

    return {
        "DraftKings": SHARP_BOOK_WEIGHTS_DK,
        "FanDuel": SHARP_BOOK_WEIGHTS_FD,
        "ESPN": SHARP_BOOK_WEIGHTS_ESPN,
    }
def _is_displayable_quote(quote: ResolvedSharpQuote) -> bool:
    """True when a per-book quote is real enough to show, even if not EV-source eligible.

    O/U quotes are always shown once resolved: exact/alt is a real posted price, and
    dk_interpolated is anchored to two real posted prices, so both are legitimate to
    display even when interpolation makes them ineligible for EV ranking. Milestone
    quotes are only shown when exact — milestone_interpolated is a ladder-derived
    synthetic price the book never actually posted, and admission status doesn't
    change that: even an unadmitted exact price is real, unlike an interpolated one.
    """
    if quote.ev_line_kind == "milestone":
        return quote.adjustment_method == "milestone_exact"
    return True


def _display_for_book(
    quote: ResolvedSharpQuote | None,
    book: str,
) -> BookQuote | None:
    if quote is None:
        return None
    if not _is_displayable_quote(quote):
        return None
    return quote.book_quote(book)


def _is_eligible_ou_quote(quote: ResolvedSharpQuote) -> bool:
    """True when the book quote is eligible O/U for EV (not milestone)."""
    return (
        quote.ev_line_kind == "ou"
        and quote.adjustment_method in EV_ELIGIBLE_ADJUSTMENT_METHODS
    )


def _is_exact_ou_at_target(quote: ResolvedSharpQuote) -> bool:
    return (
        quote.ev_line_kind == "ou"
        and quote.adjustment_method in EXACT_AT_TARGET_METHODS
    )


def _assemble_multi_book_quote(
    *,
    betr_line: float,
    book_quotes: dict[str, ResolvedSharpQuote | None],
) -> ResolvedSharpQuote | None:
    """Compose per-book columns and pick EV source per locked policy."""
    display: dict[str, BookQuote | None] = {}
    exact_books: list[tuple[str, ResolvedSharpQuote]] = []

    for cfg in SHARP_BOOKS:
        book = cfg.name
        quote = book_quotes.get(book)
        display[book] = _display_for_book(quote, book)
        if quote is not None and _is_exact_ou_at_target(quote):
            exact_books.append((book, quote))

    active_exact = [item for item in exact_books if item[1] is not None]
    if len(active_exact) >= 2:
        consensus = _consensus_sharp_quote(betr_line=betr_line, quotes=active_exact)
        consensus_sharp_books = tuple(book for book, _ in active_exact)
        consensus_sharp_by_book = tuple(
            (book, (bq.line_source or "exact") if (bq := display[book]) else "exact")
            for book, _ in active_exact
        )
        ref_quote = active_exact[0][1]
        consensus_per_book = tuple(
            (book, bq)
            for book, _ in active_exact
            if (bq := display[book]) is not None
        )
        return ResolvedSharpQuote(
            over_odds=consensus.over_odds,
            under_odds=consensus.under_odds,
            dk_line=betr_line,
            betr_line=betr_line,
            adjustment_method="multi_book_consensus",
            corroborated=True,
            dk_main_line=ref_quote.dk_main_line,
            ev_line_kind="ou",
            per_book=consensus_per_book,
            sharp_books=consensus_sharp_books,
            sharp_by_book=consensus_sharp_by_book,
            sharp_event_start=consensus.sharp_event_start,
            fair_over=consensus.fair_over,
            fair_under=consensus.fair_under,
        )

    ev_quote: ResolvedSharpQuote | None = None
    line_source: str | None = None
    for cfg in SHARP_BOOKS:
        quote = book_quotes.get(cfg.name)
        if quote is not None and _is_eligible_ou_quote(quote):
            ev_quote = quote
            line_source = quote.adjustment_method
            break

    if ev_quote is None:
        for cfg in SHARP_BOOKS:
            quote = book_quotes.get(cfg.name)
            if (
                quote is not None
                and is_ev_eligible_quote(quote)
                and quote.ev_line_kind == "milestone"
            ):
                ev_quote = quote
                line_source = "milestone_exact"
                break
        if ev_quote is None:
            return None

    ev_sharp_books: list[str] = []
    ev_sharp_by_book: list[tuple[str, str]] = []
    for cfg in SHARP_BOOKS:
        book = cfg.name
        bq = display.get(book)
        if bq and (bq.over_odds is not None or bq.under_odds is not None):
            ev_sharp_books.append(book)
            if bq.line_source:
                ev_sharp_by_book.append((book, bq.line_source or "exact"))

    per_book = tuple(
        (book, bq)
        for cfg in SHARP_BOOKS
        for book in (cfg.name,)
        if (bq := display.get(book)) is not None
        and (bq.over_odds is not None or bq.under_odds is not None)
    )

    assert ev_quote is not None and line_source is not None
    return ResolvedSharpQuote(
        over_odds=ev_quote.over_odds,
        under_odds=ev_quote.under_odds,
        dk_line=ev_quote.dk_line,
        betr_line=betr_line,
        adjustment_method=line_source,
        corroborated=ev_quote.corroborated,
        dk_main_line=ev_quote.dk_main_line,
        ev_line_kind=ev_quote.ev_line_kind,
        per_book=per_book,
        sharp_books=tuple(ev_sharp_books),
        milestone_admitted=ev_quote.milestone_admitted,
        milestone_devig_method=ev_quote.milestone_devig_method,
        sharp_by_book=tuple(ev_sharp_by_book),
        sharp_event_start=ev_quote.sharp_event_start,
    )
def _consensus_sharp_quote(
    *,
    betr_line: float,
    quotes: list[tuple[str, ResolvedSharpQuote]],
) -> ResolvedSharpQuote:
    """Weighted average of de-vigged fair probs across exact sharp books."""
    weights = load_sharp_book_weights()
    fair_pairs: list[tuple[float, float, float]] = []
    for book, quote in quotes:
        fair = _fair_probs_from_odds(quote.over_odds, quote.under_odds or 0)
        weight = weights.get(book, 1.0)
        fair_pairs.append((fair[0], fair[1], weight))
    total_weight = sum(weight for _, _, weight in fair_pairs)
    if total_weight <= 0:
        total_weight = float(len(fair_pairs))
        fair_pairs = [(over, under, 1.0) for over, under, _ in fair_pairs]
    fair_over = sum(over * weight for over, _, weight in fair_pairs) / total_weight
    fair_under = sum(under * weight for _, under, weight in fair_pairs) / total_weight
    norm = fair_over + fair_under
    if norm > 0:
        fair_over /= norm
        fair_under /= norm
    over_odds, under_odds = _odds_from_fair_probs(fair_over, fair_under)

    ref_quote: ResolvedSharpQuote | None = None
    for cfg in SHARP_BOOKS:
        for book, quote in quotes:
            if book == cfg.name:
                ref_quote = quote
                break
        if ref_quote is not None:
            break
    ref_quote = ref_quote or quotes[0][1]

    sharp_books = tuple(book for book, _ in quotes)
    event_start = next(
        (q.sharp_event_start for _, q in quotes if q.sharp_event_start),
        None,
    )
    per_book = tuple(
        (book, bq)
        for book, quote in quotes
        if (bq := _display_for_book(quote, book)) is not None
    )
    return ResolvedSharpQuote(
        over_odds=over_odds,
        under_odds=under_odds,
        dk_line=betr_line,
        betr_line=betr_line,
        adjustment_method="multi_book_consensus",
        corroborated=True,
        dk_main_line=ref_quote.dk_main_line,
        ev_line_kind="ou",
        per_book=per_book,
        sharp_books=sharp_books,
        sharp_event_start=event_start,
        fair_over=fair_over,
        fair_under=fair_under,
    )


def resolve_multi_book_sharp_quote(
    betr_prop: dict,
    dk_ou_ladder: dict[str, dict[float, dict[str, Any]]],
    fd_ou_ladder: dict[str, dict[float, dict[str, Any]]],
    *,
    normalize_player_name,
    milestone_ladder: dict[str, dict[float, dict[str, Any]]] | None = None,
    dk_milestone_ladder: dict[str, dict[float, dict[str, Any]]] | None = None,
    fd_milestone_ladder: dict[str, dict[float, dict[str, Any]]] | None = None,
    espn_ou_ladder: dict[str, dict[float, dict[str, Any]]] | None = None,
    espn_milestone_ladder: dict[str, dict[float, dict[str, Any]]] | None = None,
) -> tuple[ResolvedSharpQuote | None, str | None]:
    """
    Resolve DK + FanDuel (+ optional ESPN) sharp prices independently per book.

    Each book prefers O/U (exact/alt/interpolated for DK; exact/alt for FD/ESPN), else
    milestone when O/U is missing. EV from consensus when
    two or more books have exact O/U, else best eligible O/U (DK preferred), else
    admitted milestone. Cross-book milestone is display-only when another book supplies EV O/U.
    """
    dk_ms = dk_milestone_ladder if dk_milestone_ladder is not None else milestone_ladder
    fd_ms = fd_milestone_ladder if fd_milestone_ladder is not None else {}
    ou_ladders = {
        "DraftKings": dk_ou_ladder,
        "FanDuel": fd_ou_ladder,
    }
    if espn_ou_ladder is not None:
        ou_ladders["ESPN"] = espn_ou_ladder

    dk_quote, dk_reason = resolve_book_sharp_quote(
        "DraftKings",
        betr_prop,
        dk_ou_ladder,
        dk_ms,
        normalize_player_name=normalize_player_name,
        ou_ladders=ou_ladders,
    )
    fd_quote, fd_reason = resolve_book_sharp_quote(
        "FanDuel",
        betr_prop,
        fd_ou_ladder,
        fd_ms or None,
        normalize_player_name=normalize_player_name,
        ou_ladders=ou_ladders,
    )
    espn_ms = espn_milestone_ladder if espn_milestone_ladder is not None else {}
    espn_quote: ResolvedSharpQuote | None = None
    espn_reason: str | None = None
    if espn_ou_ladder is not None or espn_milestone_ladder:
        espn_quote, espn_reason = resolve_book_sharp_quote(
            "ESPN",
            betr_prop,
            espn_ou_ladder or {},
            espn_ms or None,
            normalize_player_name=normalize_player_name,
            ou_ladders=ou_ladders,
        )

    target_line = float(betr_prop["line"])
    assembled = _assemble_multi_book_quote(
        betr_line=target_line,
        book_quotes={
            "DraftKings": dk_quote,
            "FanDuel": fd_quote,
            "ESPN": espn_quote,
        },
    )
    if assembled is not None:
        return assembled, None
    return None, espn_reason or fd_reason or dk_reason or "no_sharp_market"
