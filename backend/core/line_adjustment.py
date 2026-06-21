"""Align DraftKings prices to Betr lines via exact alt, interpolation, or extrapolation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

from loguru import logger

from utils.math_utils import american_to_implied, multiplicative_devig

# Logit shift applied per 1.0 point of line gap (target - anchor) by market.
EXTRAPOLATION_LOGIT_SHIFT_PER_POINT: dict[str, float] = {
    "points": 0.12,
    "rebounds": 0.10,
    "assists": 0.10,
    "threes": 0.11,
    "steals": 0.11,
    "blocks": 0.11,
    "stl+blk": 0.10,
    "pra": 0.09,
    "pts+reb": 0.09,
    "pts+ast": 0.09,
    "reb+ast": 0.09,
    "hits": 0.08,
    "total_bases": 0.08,
    "h+r+rbi": 0.08,
    "singles": 0.08,
    "default": 0.08,
}

DkLineKind = Literal["ou", "milestone"]

# Sharp quotes eligible for +EV ranking.
EV_ELIGIBLE_ADJUSTMENT_METHODS: frozenset[str] = frozenset(
    {
        "exact",
        "dk_alt",
        "dk_interpolated",
        "fd_exact",
        "fd_alt",
        "multi_book_consensus",
    }
)

# True O/U at the Betr target line (not interpolated) — used for multi-book consensus.
EXACT_AT_TARGET_METHODS: frozenset[str] = frozenset(
    {"exact", "dk_alt", "fd_exact", "fd_alt"}
)

def load_sharp_book_weights() -> dict[str, float]:
    """
    Per-book weights for multi-book consensus (env-tunable; equal 1.0 defaults).

    When adding a third sharp book, extend this dict and each book's eligibility
    rules (FD: exact O/U only; DK: O/U ladder + milestone fallback; etc.).
    """
    from config.settings import SHARP_BOOK_WEIGHTS_DK, SHARP_BOOK_WEIGHTS_FD

    return {
        "DraftKings": SHARP_BOOK_WEIGHTS_DK,
        "FanDuel": SHARP_BOOK_WEIGHTS_FD,
    }


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
    dk_line_kind: DkLineKind = "ou"
    fd_line_kind: DkLineKind = "ou"
    dk_over_odds: int | None = None
    dk_under_odds: int | None = None
    fd_over_odds: int | None = None
    fd_under_odds: int | None = None
    sharp_books: tuple[str, ...] = ()
    milestone_admitted: bool = False
    milestone_devig_method: str | None = None
    dk_milestone_one_sided: bool = False
    fd_milestone_one_sided: bool = False
    dk_line_source: str | None = None
    fd_line_source: str | None = None
    sharp_by_book: tuple[tuple[str, str], ...] = ()
    sharp_event_start: str | None = None


def is_ev_eligible_quote(quote: ResolvedSharpQuote) -> bool:
    """True when the sharp quote is eligible for +EV ranking."""
    if quote.adjustment_method == "ou_ms_combo":
        return True
    if quote.dk_line_kind == "milestone":
        return (
            quote.adjustment_method == "dk_milestone_exact"
            and quote.milestone_admitted
        )
    return quote.adjustment_method in EV_ELIGIBLE_ADJUSTMENT_METHODS


def _logit(probability: float) -> float:
    clamped = min(max(probability, 1e-6), 1 - 1e-6)
    return math.log(clamped / (1 - clamped))


def _inv_logit(value: float) -> float:
    return 1 / (1 + math.exp(-value))


def _interp_logit(p_low: float, p_high: float, weight_high: float) -> float:
    """Linear interpolation in logit space; weight_high=1 -> p_high."""
    weight_high = min(max(weight_high, 0.0), 1.0)
    low = _logit(p_low)
    high = _logit(p_high)
    return _inv_logit((1 - weight_high) * low + weight_high * high)


def _shift_per_point(market: str) -> float:
    return EXTRAPOLATION_LOGIT_SHIFT_PER_POINT.get(
        market, EXTRAPOLATION_LOGIT_SHIFT_PER_POINT["default"]
    )


def normalize_game_key(game: str) -> str:
    """Canonical matchup key (e.g. CIN@NYY) for cross-book ladder lookup."""
    return game.strip().upper()


def _hour_floor(iso: str) -> str:
    """Hour-precision prefix of an ISO UTC timestamp (e.g. 2026-06-19T17)."""
    return iso[:13] if iso else ""


def build_match_context_key(
    prop: dict,
    *,
    normalize_player_name,
) -> str:
    """
    Canonical match-context key: player|market|league|[game]|[event_hour]|[live].

    Line-agnostic; ``event_hour`` is UTC hour-floor (``iso[:13]``) when
    ``event_start`` is present. Live rows without ``event_start`` omit the hour.
    """
    key = f"{normalize_player_name(prop['player'])}|{prop['market']}"
    league = prop.get("league")
    if league:
        key = f"{key}|{str(league).upper()}"
    game = prop.get("game")
    if game:
        key = f"{key}|{normalize_game_key(game)}"
    event_start = prop.get("event_start", "")
    if event_start:
        key = f"{key}|{_hour_floor(event_start)}"
    if prop.get("is_live"):
        key = f"{key}|live"
    return key


def _event_start_from_row(row: dict[str, Any]) -> str | None:
    start = row.get("event_start") or ""
    return start if start else None


def build_player_market_key(
    prop: dict,
    *,
    normalize_player_name,
) -> str:
    """
    Player + market ladder key, optionally scoped by game and live snapshot.

    Live Betr rows carry ``is_live``; sharp books tag live DK rows the same way.
    Pregame rows omit the live suffix so back-to-back matchups (same teams, different
    dates) do not collide with in-progress DFS props.
    """
    key = f"{normalize_player_name(prop['player'])}|{prop['market']}"
    game = prop.get("game")
    if game:
        key = f"{key}|{normalize_game_key(game)}"
    if prop.get("is_live"):
        key = f"{key}|live"
    return key


def build_player_market_ladder(
    dk_props: list[dict],
    *,
    normalize_player_name,
) -> dict[str, dict[float, dict[str, Any]]]:
    """Index DK O/U rows by player|market -> line -> odds metadata."""
    ladder: dict[str, dict[float, dict[str, Any]]] = {}
    for prop in dk_props:
        if prop.get("line_kind", "ou") == "milestone":
            continue
        over_odds = prop.get("over_odds")
        under_odds = prop.get("under_odds")
        if over_odds is None or under_odds is None:
            continue
        pm_key = build_player_market_key(prop, normalize_player_name=normalize_player_name)
        line = float(prop["line"])
        bucket = ladder.setdefault(pm_key, {})
        if line in bucket:
            logger.warning(
                "sharp O/U ladder collision pm_key={pm_key} line={line} "
                "event_start={event_start}",
                pm_key=pm_key,
                line=line,
                event_start=prop.get("event_start", ""),
            )
        bucket[line] = {
            "over_odds": int(over_odds),
            "under_odds": int(under_odds),
            "is_main_line": bool(prop.get("is_main_line", True)),
            "event_start": prop.get("event_start", ""),
        }
    return ladder


def build_milestone_ladder(
    sharp_props: list[dict],
    *,
    normalize_player_name,
) -> dict[str, dict[float, dict[str, Any]]]:
    """Index milestone (N+) rows by player|market -> converted line -> over odds."""
    ladder: dict[str, dict[float, dict[str, Any]]] = {}
    for prop in sharp_props:
        if prop.get("line_kind") != "milestone":
            continue
        over_odds = prop.get("over_odds")
        if over_odds is None:
            continue
        pm_key = build_player_market_key(prop, normalize_player_name=normalize_player_name)
        line = float(prop["line"])
        source_book = prop.get("sportsbook", "DraftKings")
        bucket = ladder.setdefault(pm_key, {})
        if line in bucket:
            logger.warning(
                "sharp milestone ladder collision pm_key={pm_key} line={line} "
                "event_start={event_start}",
                pm_key=pm_key,
                line=line,
                event_start=prop.get("event_start", ""),
            )
        bucket[line] = {
            "over_odds": int(over_odds),
            "milestone_threshold": prop.get("milestone_threshold"),
            "is_main_line": bool(prop.get("is_main_line", True)),
            "sportsbook": source_book,
            "event_start": prop.get("event_start", ""),
        }
    return ladder


def build_milestone_ladders(
    sharp_props: list[dict],
    *,
    normalize_player_name,
) -> dict[str, dict[str, dict[float, dict[str, Any]]]]:
    """Per-book milestone ladders keyed by sportsbook name."""
    ladders: dict[str, dict[str, dict[float, dict[str, Any]]]] = {}
    for prop in sharp_props:
        if prop.get("line_kind") != "milestone":
            continue
        over_odds = prop.get("over_odds")
        if over_odds is None:
            continue
        source_book = prop.get("sportsbook", "DraftKings")
        pm_key = build_player_market_key(prop, normalize_player_name=normalize_player_name)
        line = float(prop["line"])
        bucket = ladders.setdefault(source_book, {}).setdefault(pm_key, {})
        if line in bucket:
            logger.warning(
                "sharp per-book milestone collision book={book} pm_key={pm_key} "
                "line={line} event_start={event_start}",
                book=source_book,
                pm_key=pm_key,
                line=line,
                event_start=prop.get("event_start", ""),
            )
        bucket[line] = {
            "over_odds": int(over_odds),
            "milestone_threshold": prop.get("milestone_threshold"),
            "is_main_line": bool(prop.get("is_main_line", True)),
            "sportsbook": source_book,
            "event_start": prop.get("event_start", ""),
        }
    return ladders


def merge_milestone_ladders(
    ladders: dict[str, dict[str, dict[float, dict[str, Any]]]],
    *,
    book_precedence: tuple[str, ...] = ("DraftKings", "FanDuel"),
) -> dict[str, dict[float, dict[str, Any]]]:
    """Merge per-book milestone ladders; earlier books win on line collisions."""
    merged: dict[str, dict[float, dict[str, Any]]] = {}
    for book in book_precedence:
        for pm_key, lines in ladders.get(book, {}).items():
            merged.setdefault(pm_key, {})
            for line, row in lines.items():
                if line not in merged[pm_key]:
                    merged[pm_key][line] = row
    return merged


def _milestone_raw_book_odds(
    source_book: str,
    raw_over: int,
) -> dict[str, int | None]:
    """Map raw milestone over odds to the correct per-book display fields."""
    if source_book == "FanDuel":
        return {
            "dk_over_odds": None,
            "dk_under_odds": None,
            "fd_over_odds": raw_over,
            "fd_under_odds": None,
        }
    return {
        "dk_over_odds": raw_over,
        "dk_under_odds": None,
        "fd_over_odds": None,
        "fd_under_odds": None,
    }


def estimate_ou_hold(
    ou_ladders: dict[str, dict[str, dict[float, dict[str, Any]]]],
    pm_key: str,
    *,
    preferred_book: str | None = None,
    source_book_only: bool = False,
) -> float | None:
    """Average two-sided hold for a player|market across O/U rows; None when no O/U exists."""
    book_order = list(ou_ladders.keys())
    if preferred_book and preferred_book in ou_ladders:
        book_order = [preferred_book] + [
            book for book in book_order if book != preferred_book
        ]
    if source_book_only and preferred_book:
        book_order = [preferred_book]

    holds: list[float] = []
    for book in book_order:
        lines = ou_ladders.get(book, {}).get(pm_key)
        if not lines:
            continue
        for row in lines.values():
            over_odds = row.get("over_odds")
            under_odds = row.get("under_odds")
            if over_odds is None or under_odds is None:
                continue
            over_implied = american_to_implied(int(over_odds))
            under_implied = american_to_implied(int(under_odds))
            holds.append(over_implied + under_implied - 1.0)
        if holds:
            return sum(holds) / len(holds)
    return None


def _contiguous_milestone_segment(
    sorted_lines: list[float],
    target_line: float,
    *,
    step: float = 1.0,
) -> list[float] | None:
    """Return the contiguous ladder segment containing target_line, or None."""
    if target_line not in sorted_lines:
        return None
    idx = sorted_lines.index(target_line)
    start = idx
    while start > 0 and abs(sorted_lines[start] - sorted_lines[start - 1] - step) < 1e-9:
        start -= 1
    end = idx
    while (
        end < len(sorted_lines) - 1
        and abs(sorted_lines[end + 1] - sorted_lines[end] - step) < 1e-9
    ):
        end += 1
    segment = sorted_lines[start : end + 1]
    if len(segment) >= 2:
        return segment
    return None


def _survival_at_line(
    segment: list[float],
    lines: dict[float, dict[str, Any]],
    target_line: float,
) -> float:
    """Fair P(X >= threshold) from renormalized PMF masses on a milestone ladder."""
    survivals = [american_to_implied(lines[line]["over_odds"]) for line in segment]
    masses = [1.0 - survivals[0]]
    masses.extend(s - survivals[i + 1] for i, s in enumerate(survivals[:-1]))
    masses.append(survivals[-1])
    masses = [max(0.0, mass) for mass in masses]
    total = sum(masses)
    if total <= 0:
        return american_to_implied(lines[target_line]["over_odds"])
    masses = [mass / total for mass in masses]
    target_idx = segment.index(target_line)
    if target_idx + 1 >= len(masses):
        return masses[-1]
    return sum(masses[target_idx + 1 :])


def devig_milestone_fair_over(
    lines: dict[float, dict[str, Any]],
    target_line: float,
    *,
    market: str,
    ou_hold: float | None,
) -> tuple[float, str]:
    """
    De-vig a milestone over-only price via ladder normalization or hold shrink.

    Returns (fair_over_probability, method_name).
    """
    from config.settings import MILESTONE_ASSUMED_HOLD

    _ = market  # reserved for market-specific ladder steps if needed later
    sorted_lines = sorted(lines.keys())
    segment = _contiguous_milestone_segment(sorted_lines, target_line)
    if segment is not None:
        return _survival_at_line(segment, lines, target_line), "ladder_normalized"

    raw = american_to_implied(lines[target_line]["over_odds"])
    hold = ou_hold if ou_hold is not None else MILESTONE_ASSUMED_HOLD
    return raw * (1.0 - hold / 2.0), "hold_shrink"


def _fair_probs_from_odds(over_odds: int, under_odds: int) -> tuple[float, float]:
    return multiplicative_devig(over_odds, under_odds)


def _fair_over_from_milestone(over_odds: int) -> float:
    return american_to_implied(over_odds)


def _odds_from_fair_probs(fair_over: float, fair_under: float) -> tuple[int, int]:
    from utils.math_utils import implied_to_american

    return implied_to_american(fair_over), implied_to_american(fair_under)


def _extrapolate_fair_probs(
    fair_over: float,
    fair_under: float,
    *,
    anchor_line: float,
    target_line: float,
    market: str,
) -> tuple[float, float]:
    """
    Shift fair probs from anchor_line to target_line.

    Lower target vs anchor -> higher over / lower under probability.
    """
    gap = anchor_line - target_line
    shift = _shift_per_point(market) * gap
    fair_over = _inv_logit(_logit(fair_over) + shift)
    fair_under = _inv_logit(_logit(fair_under) - shift)
    total = fair_over + fair_under
    if total <= 0:
        return fair_over, fair_under
    return fair_over / total, fair_under / total


def _extrapolate_milestone_fair_over(
    fair_over: float,
    *,
    anchor_line: float,
    target_line: float,
    market: str,
) -> float:
    gap = anchor_line - target_line
    shift = _shift_per_point(market) * gap
    return _inv_logit(_logit(fair_over) + shift)


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
        return (
            ResolvedSharpQuote(
                over_odds=row["over_odds"],
                under_odds=row["under_odds"],
                dk_line=target_line,
                betr_line=target_line,
                adjustment_method=method,
                corroborated=True,
                dk_main_line=dk_main_line,
                dk_line_kind="ou",
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
        return (
            ResolvedSharpQuote(
                over_odds=over_odds,
                under_odds=under_odds,
                dk_line=target_line,
                betr_line=target_line,
                adjustment_method="dk_interpolated",
                corroborated=True,
                dk_main_line=dk_main_line,
                dk_line_kind="ou",
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
    return (
        ResolvedSharpQuote(
            over_odds=over_odds,
            under_odds=under_odds,
            dk_line=anchor_line,
            betr_line=target_line,
            adjustment_method="dk_extrapolated",
            corroborated=False,
            dk_main_line=dk_main_line,
            dk_line_kind="ou",
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
        devigged_over, _ = _odds_from_fair_probs(fair_over, 1.0 - fair_over)
        admitted = fair_over >= MILESTONE_MIN_FAIR_OVER
        book_odds = _milestone_raw_book_odds(source_book, int(row["over_odds"]))
        return (
            ResolvedSharpQuote(
                over_odds=devigged_over,
                under_odds=None,
                dk_line=target_line,
                betr_line=target_line,
                adjustment_method="dk_milestone_exact",
                corroborated=False,
                dk_main_line=dk_main_line,
                dk_line_kind="milestone",
                sharp_books=(source_book,),
                milestone_admitted=admitted,
                milestone_devig_method=devig_method,
                sharp_event_start=_event_start_from_row(row),
                **book_odds,
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
        return (
            ResolvedSharpQuote(
                over_odds=over_odds,
                under_odds=None,
                dk_line=target_line,
                betr_line=target_line,
                adjustment_method="dk_milestone_interpolated",
                corroborated=False,
                dk_main_line=dk_main_line,
                dk_line_kind="milestone",
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
    return (
        ResolvedSharpQuote(
            over_odds=over_odds,
            under_odds=None,
            dk_line=anchor_line,
            betr_line=target_line,
            adjustment_method="dk_milestone_extrapolated",
            corroborated=False,
            dk_main_line=dk_main_line,
            dk_line_kind="milestone",
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


def _resolve_fd_exact_quote(
    betr_prop: dict,
    fd_ladder: dict[str, dict[float, dict[str, Any]]],
    *,
    normalize_player_name,
) -> tuple[ResolvedSharpQuote | None, str | None]:
    """Resolve FanDuel O/U only when an exact alt or main line exists at the Betr line."""
    target_line = float(betr_prop["line"])
    pm_key = build_player_market_key(
        betr_prop, normalize_player_name=normalize_player_name
    )
    lines = fd_ladder.get(pm_key)
    if not lines:
        return None, "no_fd_market"
    if target_line not in lines:
        return None, "no_fd_exact_line"

    row = lines[target_line]
    main_lines = sorted(
        line for line, entry in lines.items() if entry.get("is_main_line", True)
    )
    fd_main_line = main_lines[0] if main_lines else None
    method = "fd_alt" if not row.get("is_main_line", True) else "fd_exact"
    return (
        ResolvedSharpQuote(
            over_odds=row["over_odds"],
            under_odds=row["under_odds"],
            dk_line=target_line,
            betr_line=target_line,
            adjustment_method=method,
            corroborated=True,
            dk_main_line=fd_main_line,
            dk_line_kind="ou",
            fd_over_odds=row["over_odds"],
            fd_under_odds=row["under_odds"],
            sharp_books=("FanDuel",),
            sharp_event_start=_event_start_from_row(row),
        ),
        None,
    )


def _is_eligible_ou_quote(quote: ResolvedSharpQuote) -> bool:
    """True when the book quote is eligible O/U for EV (not milestone)."""
    return (
        quote.dk_line_kind == "ou"
        and quote.adjustment_method in EV_ELIGIBLE_ADJUSTMENT_METHODS
    )


def _is_exact_ou_at_target(quote: ResolvedSharpQuote) -> bool:
    return (
        quote.dk_line_kind == "ou"
        and quote.adjustment_method in EXACT_AT_TARGET_METHODS
    )


def _book_quote_display_odds(
    quote: ResolvedSharpQuote | None,
    book: str,
) -> tuple[int | None, int | None, DkLineKind, bool, str | None]:
    """Per-book column odds, line kind, milestone-one-sided flag, and method."""
    if quote is None:
        return None, None, "ou", False, None
    method = quote.adjustment_method
    if quote.dk_line_kind == "milestone":
        if book == "FanDuel":
            over = quote.fd_over_odds
            under = quote.fd_under_odds
        else:
            over = quote.dk_over_odds
            under = quote.dk_under_odds
        return over, under, "milestone", over is not None and under is None, method
    if book == "FanDuel":
        over = quote.fd_over_odds if quote.fd_over_odds is not None else quote.over_odds
        under = (
            quote.fd_under_odds if quote.fd_under_odds is not None else quote.under_odds
        )
    else:
        over = quote.dk_over_odds if quote.dk_over_odds is not None else quote.over_odds
        under = (
            quote.dk_under_odds if quote.dk_under_odds is not None else quote.under_odds
        )
    return over, under, "ou", False, method


def _milestone_exact_for_display(quote: ResolvedSharpQuote | None) -> bool:
    """True when the book has an exact milestone at the Betr line (display-only ok)."""
    return (
        quote is not None
        and quote.dk_line_kind == "milestone"
        and quote.adjustment_method == "dk_milestone_exact"
    )


def _assemble_multi_book_quote(
    *,
    betr_line: float,
    dk_book_quote: ResolvedSharpQuote | None,
    fd_book_quote: ResolvedSharpQuote | None,
) -> ResolvedSharpQuote | None:
    """Compose per-book columns and pick EV source per locked policy."""
    dk_over, dk_under, dk_kind, dk_ms_one, dk_method = _book_quote_display_odds(
        dk_book_quote, "DraftKings"
    )
    fd_over, fd_under, fd_kind, fd_ms_one, fd_method = _book_quote_display_odds(
        fd_book_quote, "FanDuel"
    )

    dk_exact = dk_book_quote is not None and _is_exact_ou_at_target(dk_book_quote)
    fd_exact = fd_book_quote is not None and _is_exact_ou_at_target(fd_book_quote)
    dk_eligible_ou = dk_book_quote is not None and _is_eligible_ou_quote(dk_book_quote)
    fd_eligible_ou = fd_book_quote is not None and _is_eligible_ou_quote(fd_book_quote)

    ev_quote: ResolvedSharpQuote | None = None
    line_source: str | None = None

    if dk_exact and fd_exact and dk_book_quote is not None and fd_book_quote is not None:
        consensus = _consensus_sharp_quote(
            betr_line=betr_line,
            dk_quote=dk_book_quote,
            fd_quote=fd_book_quote,
        )
        return ResolvedSharpQuote(
            over_odds=consensus.over_odds,
            under_odds=consensus.under_odds,
            dk_line=betr_line,
            betr_line=betr_line,
            adjustment_method="multi_book_consensus",
            corroborated=True,
            dk_main_line=dk_book_quote.dk_main_line,
            dk_line_kind="ou",
            fd_line_kind="ou",
            dk_over_odds=dk_over,
            dk_under_odds=dk_under,
            fd_over_odds=fd_over,
            fd_under_odds=fd_under,
            sharp_books=("DraftKings", "FanDuel"),
            dk_line_source=dk_method,
            fd_line_source=fd_method,
            sharp_by_book=(
                ("DraftKings", dk_method or "exact"),
                ("FanDuel", fd_method or "fd_exact"),
            ),
            sharp_event_start=dk_book_quote.sharp_event_start
            or fd_book_quote.sharp_event_start,
        )

    if dk_eligible_ou and dk_book_quote is not None:
        ev_quote = dk_book_quote
        line_source = dk_book_quote.adjustment_method
    elif fd_eligible_ou and fd_book_quote is not None:
        ev_quote = fd_book_quote
        line_source = fd_book_quote.adjustment_method
    elif (
        dk_book_quote is not None
        and is_ev_eligible_quote(dk_book_quote)
        and dk_book_quote.dk_line_kind == "milestone"
    ):
        ev_quote = dk_book_quote
        line_source = "dk_milestone_exact"
    elif (
        fd_book_quote is not None
        and is_ev_eligible_quote(fd_book_quote)
        and fd_book_quote.dk_line_kind == "milestone"
    ):
        ev_quote = fd_book_quote
        line_source = "dk_milestone_exact"
    else:
        return None

    dk_has_ms_display = _milestone_exact_for_display(dk_book_quote)
    fd_has_ms_display = _milestone_exact_for_display(fd_book_quote)
    ev_from_ou = ev_quote is not None and ev_quote.dk_line_kind == "ou"
    other_ms_only = (
        (ev_from_ou and dk_eligible_ou and fd_has_ms_display and not fd_eligible_ou)
        or (ev_from_ou and fd_eligible_ou and dk_has_ms_display and not dk_eligible_ou)
    )
    if other_ms_only:
        line_source = "ou_ms_combo"

    sharp_books: list[str] = []
    sharp_by_book: list[tuple[str, str]] = []
    if dk_book_quote is not None and (dk_over is not None or dk_under is not None):
        sharp_books.append("DraftKings")
        if dk_method:
            sharp_by_book.append(("DraftKings", dk_method))
    if fd_book_quote is not None and (fd_over is not None or fd_under is not None):
        sharp_books.append("FanDuel")
        if fd_method:
            sharp_by_book.append(("FanDuel", fd_method))

    assert ev_quote is not None and line_source is not None
    return ResolvedSharpQuote(
        over_odds=ev_quote.over_odds,
        under_odds=ev_quote.under_odds,
        dk_line=ev_quote.dk_line,
        betr_line=betr_line,
        adjustment_method=line_source,
        corroborated=ev_quote.corroborated,
        dk_main_line=ev_quote.dk_main_line,
        dk_line_kind=dk_kind,
        fd_line_kind=fd_kind,
        dk_over_odds=dk_over,
        dk_under_odds=dk_under,
        fd_over_odds=fd_over,
        fd_under_odds=fd_under,
        sharp_books=tuple(sharp_books),
        milestone_admitted=ev_quote.milestone_admitted,
        milestone_devig_method=ev_quote.milestone_devig_method,
        dk_milestone_one_sided=dk_ms_one,
        fd_milestone_one_sided=fd_ms_one,
        dk_line_source=dk_method,
        fd_line_source=fd_method,
        sharp_by_book=tuple(sharp_by_book),
        sharp_event_start=ev_quote.sharp_event_start,
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
    if book == "FanDuel":
        ou_quote, reason = _resolve_fd_exact_quote(
            betr_prop,
            ou_ladder,
            normalize_player_name=normalize_player_name,
        )
        use_milestone = milestone_ladder and ou_quote is None
        if use_milestone:
            milestone_quote, milestone_reason = _resolve_milestone_ladder(
                betr_prop,
                milestone_ladder,
                normalize_player_name=normalize_player_name,
                ou_ladders=ou_ladders,
                hold_source_book_only=True,
            )
            if milestone_quote is not None:
                return milestone_quote, None
            return None, milestone_reason or reason
        return ou_quote, reason

    ou_quote, ou_reason = _resolve_ou_ladder(
        betr_prop, ou_ladder, normalize_player_name=normalize_player_name
    )
    use_milestone = milestone_ladder and (
        ou_quote is None or ou_quote.adjustment_method == "dk_extrapolated"
    )
    if use_milestone:
        milestone_ou_ladders = ou_ladders or {book: ou_ladder}
        milestone_quote, milestone_reason = _resolve_milestone_ladder(
            betr_prop,
            milestone_ladder,
            normalize_player_name=normalize_player_name,
            ou_ladders=milestone_ou_ladders,
            hold_source_book_only=True,
        )
        if milestone_quote is not None:
            return milestone_quote, None
        if ou_quote is None:
            return None, milestone_reason or ou_reason
    if ou_quote is not None:
        return ou_quote, None
    return None, ou_reason or "no_dk_market"


def _consensus_sharp_quote(
    *,
    betr_line: float,
    dk_quote: ResolvedSharpQuote,
    fd_quote: ResolvedSharpQuote,
) -> ResolvedSharpQuote:
    """Equal-weight average of de-vigged fair probs across exact sharp books."""
    fair_dk = _fair_probs_from_odds(dk_quote.over_odds, dk_quote.under_odds or 0)
    fair_fd = _fair_probs_from_odds(fd_quote.over_odds, fd_quote.under_odds or 0)
    weights = load_sharp_book_weights()
    weight_dk = weights.get("DraftKings", 1.0)
    weight_fd = weights.get("FanDuel", 1.0)
    total_weight = weight_dk + weight_fd
    fair_over = (fair_dk[0] * weight_dk + fair_fd[0] * weight_fd) / total_weight
    fair_under = (fair_dk[1] * weight_dk + fair_fd[1] * weight_fd) / total_weight
    norm = fair_over + fair_under
    if norm > 0:
        fair_over /= norm
        fair_under /= norm
    over_odds, under_odds = _odds_from_fair_probs(fair_over, fair_under)
    return ResolvedSharpQuote(
        over_odds=over_odds,
        under_odds=under_odds,
        dk_line=betr_line,
        betr_line=betr_line,
        adjustment_method="multi_book_consensus",
        corroborated=True,
        dk_main_line=dk_quote.dk_main_line,
        dk_line_kind="ou",
        dk_over_odds=dk_quote.over_odds,
        dk_under_odds=dk_quote.under_odds,
        fd_over_odds=fd_quote.over_odds,
        fd_under_odds=fd_quote.under_odds,
        sharp_books=("DraftKings", "FanDuel"),
        sharp_event_start=dk_quote.sharp_event_start or fd_quote.sharp_event_start,
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
) -> tuple[ResolvedSharpQuote | None, str | None]:
    """
    Resolve DK + FanDuel sharp prices independently per book, assemble one quote.

    Each book prefers O/U (exact/alt/interpolated for DK; exact/alt for FD), else
    milestone when O/U is missing or DK-extrapolated only. EV from consensus when
    both exact O/U, else best eligible O/U (DK preferred), else admitted milestone.
    Cross-book milestone is display-only when the other book supplies EV O/U.
    """
    dk_ms = dk_milestone_ladder if dk_milestone_ladder is not None else milestone_ladder
    fd_ms = fd_milestone_ladder if fd_milestone_ladder is not None else {}
    ou_ladders = {"DraftKings": dk_ou_ladder, "FanDuel": fd_ou_ladder}

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

    target_line = float(betr_prop["line"])
    assembled = _assemble_multi_book_quote(
        betr_line=target_line,
        dk_book_quote=dk_quote,
        fd_book_quote=fd_quote,
    )
    if assembled is not None:
        return assembled, None
    return None, fd_reason or dk_reason or "no_sharp_market"
