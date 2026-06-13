"""Align DraftKings prices to Betr lines via exact alt, interpolation, or extrapolation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

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
    dk_over_odds: int | None = None
    dk_under_odds: int | None = None
    fd_over_odds: int | None = None
    fd_under_odds: int | None = None
    sharp_books: tuple[str, ...] = ()


def is_ev_eligible_quote(quote: ResolvedSharpQuote) -> bool:
    """True when the sharp quote uses corroborated O/U at the Betr line (no extrapolation)."""
    return (
        quote.dk_line_kind == "ou"
        and quote.adjustment_method in EV_ELIGIBLE_ADJUSTMENT_METHODS
    )


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
        player = normalize_player_name(prop["player"])
        pm_key = f"{player}|{prop['market']}"
        line = float(prop["line"])
        ladder.setdefault(pm_key, {})[line] = {
            "over_odds": int(over_odds),
            "under_odds": int(under_odds),
            "is_main_line": bool(prop.get("is_main_line", True)),
        }
    return ladder


def build_milestone_ladder(
    dk_props: list[dict],
    *,
    normalize_player_name,
) -> dict[str, dict[float, dict[str, Any]]]:
    """Index DK milestone (N+) rows by player|market -> converted line -> over odds."""
    ladder: dict[str, dict[float, dict[str, Any]]] = {}
    for prop in dk_props:
        if prop.get("line_kind") != "milestone":
            continue
        over_odds = prop.get("over_odds")
        if over_odds is None:
            continue
        player = normalize_player_name(prop["player"])
        pm_key = f"{player}|{prop['market']}"
        line = float(prop["line"])
        ladder.setdefault(pm_key, {})[line] = {
            "over_odds": int(over_odds),
            "milestone_threshold": prop.get("milestone_threshold"),
            "is_main_line": bool(prop.get("is_main_line", True)),
        }
    return ladder


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
    player = normalize_player_name(betr_prop["player"])
    market = betr_prop["market"]
    target_line = float(betr_prop["line"])
    pm_key = f"{player}|{market}"
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
        ),
        None,
    )


def _resolve_milestone_ladder(
    betr_prop: dict,
    ladder: dict[str, dict[float, dict[str, Any]]],
    *,
    normalize_player_name,
) -> tuple[ResolvedSharpQuote | None, str | None]:
    """Resolve using DK milestone (N+) over-only lines."""
    player = normalize_player_name(betr_prop["player"])
    market = betr_prop["market"]
    target_line = float(betr_prop["line"])
    pm_key = f"{player}|{market}"
    lines = ladder.get(pm_key)
    if not lines:
        return None, "no_dk_market"

    main_lines = sorted(
        line for line, row in lines.items() if row.get("is_main_line", True)
    )
    dk_main_line = main_lines[0] if main_lines else None

    if target_line in lines:
        row = lines[target_line]
        return (
            ResolvedSharpQuote(
                over_odds=row["over_odds"],
                under_odds=None,
                dk_line=target_line,
                betr_line=target_line,
                adjustment_method="dk_milestone_exact",
                corroborated=False,
                dk_main_line=dk_main_line,
                dk_line_kind="milestone",
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
        ),
        None,
    )


def resolve_sharp_quote(
    betr_prop: dict,
    ou_ladder: dict[str, dict[float, dict[str, Any]]],
    *,
    normalize_player_name,
    milestone_ladder: dict[str, dict[float, dict[str, Any]]] | None = None,
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
        milestone_quote, milestone_reason = _resolve_milestone_ladder(
            betr_prop,
            milestone_ladder,
            normalize_player_name=normalize_player_name,
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
    player = normalize_player_name(betr_prop["player"])
    market = betr_prop["market"]
    target_line = float(betr_prop["line"])
    pm_key = f"{player}|{market}"
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
        ),
        None,
    )


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
    )


def resolve_multi_book_sharp_quote(
    betr_prop: dict,
    dk_ou_ladder: dict[str, dict[float, dict[str, Any]]],
    fd_ou_ladder: dict[str, dict[float, dict[str, Any]]],
    *,
    normalize_player_name,
    milestone_ladder: dict[str, dict[float, dict[str, Any]]] | None = None,
) -> tuple[ResolvedSharpQuote | None, str | None]:
    """
    Resolve DK + FanDuel sharp prices for a Betr prop.

    FanDuel contributes exact main/alt lines only. When both books have exact
    O/U at the Betr line, fair probs are de-vigged per book and combined with
    configurable weight (see load_sharp_book_weights — extend when adding books).
    """
    dk_quote, dk_reason = resolve_sharp_quote(
        betr_prop,
        dk_ou_ladder,
        normalize_player_name=normalize_player_name,
        milestone_ladder=milestone_ladder,
    )
    fd_quote, fd_reason = _resolve_fd_exact_quote(
        betr_prop,
        fd_ou_ladder,
        normalize_player_name=normalize_player_name,
    )

    dk_exact = (
        dk_quote is not None
        and dk_quote.adjustment_method in EXACT_AT_TARGET_METHODS
        and dk_quote.dk_line_kind == "ou"
    )
    fd_exact = fd_quote is not None

    if dk_exact and fd_exact and dk_quote is not None and fd_quote is not None:
        target_line = float(betr_prop["line"])
        return (
            _consensus_sharp_quote(
                betr_line=target_line,
                dk_quote=dk_quote,
                fd_quote=fd_quote,
            ),
            None,
        )

    if fd_exact and fd_quote is not None:
        if dk_quote is None or dk_quote.adjustment_method == "dk_interpolated":
            return fd_quote, None
        if not is_ev_eligible_quote(dk_quote):
            return fd_quote, None

    if dk_quote is not None:
        if dk_quote.adjustment_method in {"exact", "dk_alt", "dk_interpolated"}:
            enriched = ResolvedSharpQuote(
                over_odds=dk_quote.over_odds,
                under_odds=dk_quote.under_odds,
                dk_line=dk_quote.dk_line,
                betr_line=dk_quote.betr_line,
                adjustment_method=dk_quote.adjustment_method,
                corroborated=dk_quote.corroborated,
                dk_main_line=dk_quote.dk_main_line,
                dk_line_kind=dk_quote.dk_line_kind,
                dk_over_odds=dk_quote.over_odds,
                dk_under_odds=dk_quote.under_odds,
                sharp_books=("DraftKings",),
            )
            return enriched, None
        if is_ev_eligible_quote(dk_quote):
            return dk_quote, None
        return None, "no_exact_sharp_line"

    if fd_quote is not None:
        return fd_quote, None
    return None, fd_reason or dk_reason or "no_sharp_market"
