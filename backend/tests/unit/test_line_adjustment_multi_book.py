import pytest

from core.engine import find_ev_opportunities
from core.line_adjustment import (
    build_player_market_ladder,
    resolve_multi_book_sharp_quote,
)
from core.engine import normalize_player_name


def _betr(player: str, market: str, line: float) -> dict:
    return {
        "sportsbook": "Betr",
        "player": player,
        "market": market,
        "line": line,
        "over_odds": -120,
        "under_odds": -120,
    }


def _dk(player: str, market: str, line: float, over: int, under: int, *, main=True) -> dict:
    return {
        "sportsbook": "DraftKings",
        "player": player,
        "market": market,
        "line": line,
        "over_odds": over,
        "under_odds": under,
        "is_main_line": main,
    }


def _fd(player: str, market: str, line: float, over: int, under: int, *, main=True) -> dict:
    return {
        "sportsbook": "FanDuel",
        "player": player,
        "market": market,
        "line": line,
        "over_odds": over,
        "under_odds": under,
        "is_main_line": main,
    }


def test_multi_book_consensus_when_both_exact_at_betr_line():
    betr = _betr("Test Player", "points", 22.5)
    dk_ladder = build_player_market_ladder(
        [_dk("Test Player", "points", 22.5, -130, 110, main=False)],
        normalize_player_name=normalize_player_name,
    )
    fd_ladder = build_player_market_ladder(
        [_fd("Test Player", "points", 22.5, -120, -110, main=False)],
        normalize_player_name=normalize_player_name,
    )

    quote, reason = resolve_multi_book_sharp_quote(
        betr,
        dk_ladder,
        fd_ladder,
        normalize_player_name=normalize_player_name,
    )

    assert reason is None
    assert quote is not None
    assert quote.adjustment_method == "multi_book_consensus"
    assert quote.sharp_books == ("DraftKings", "FanDuel")
    assert quote.dk_over_odds == -130
    assert quote.fd_over_odds == -120


def test_fd_exact_preferred_over_dk_interpolation():
    betr = _betr("Test Player", "points", 22.5)
    dk_props = [
        _dk("Test Player", "points", 20.5, -110, -110),
        _dk("Test Player", "points", 24.5, -110, -110),
    ]
    dk_ladder = build_player_market_ladder(
        dk_props, normalize_player_name=normalize_player_name
    )
    fd_ladder = build_player_market_ladder(
        [_fd("Test Player", "points", 22.5, -115, -115, main=False)],
        normalize_player_name=normalize_player_name,
    )

    quote, _ = resolve_multi_book_sharp_quote(
        betr,
        dk_ladder,
        fd_ladder,
        normalize_player_name=normalize_player_name,
    )

    assert quote is not None
    assert quote.adjustment_method == "fd_alt"
    assert quote.fd_over_odds == -115


def test_fd_only_exact_unlocks_ev_when_dk_missing():
    betr = [_betr("Test Player", "points", 22.5)]
    dk = [_dk("Other Player", "points", 22.5, -110, -110)]
    fd = [_fd("Test Player", "points", 22.5, -140, 120, main=False)]

    results = find_ev_opportunities(betr, dk, fanduel_props=fd, min_ev=0.0)

    assert results
    assert results[0]["line_source"] == "fd_alt"
    assert results[0]["fd_over_odds"] == -140
    assert results[0]["dk_over_odds"] is None
    assert results[0]["sharp_books"] == ["FanDuel"]
