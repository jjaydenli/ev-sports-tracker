import pytest

from core.engine import find_ev_opportunities, normalize_player_name
from core.line_adjustment import (
    _consensus_sharp_quote,
    build_milestone_ladders,
    build_player_market_ladder,
    load_sharp_book_weights,
    resolve_multi_book_sharp_quote,
    ResolvedSharpQuote,
)


_EVENT_START = "2026-06-19T23:00:00.000Z"


def _betr(player: str, market: str, line: float) -> dict:
    return {
        "sportsbook": "Betr",
        "player": player,
        "market": market,
        "line": line,
        "over_odds": -120,
        "under_odds": -120,
        "event_start": _EVENT_START,
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
        "event_start": _EVENT_START,
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
        "event_start": _EVENT_START,
    }


def test_load_sharp_book_weights_defaults():
    weights = load_sharp_book_weights()
    assert weights["DraftKings"] == 1.0
    assert weights["FanDuel"] == 1.0
    assert weights["ESPN"] == 1.0


def test_consensus_weights_skew_toward_heavier_book(monkeypatch):
    monkeypatch.setattr("config.settings.SHARP_BOOK_WEIGHTS_DK", 3.0)
    monkeypatch.setattr("config.settings.SHARP_BOOK_WEIGHTS_FD", 1.0)

    dk_quote = ResolvedSharpQuote(
        over_odds=-200,
        under_odds=170,
        dk_line=22.5,
        betr_line=22.5,
        adjustment_method="exact",
        corroborated=True,
        dk_main_line=22.5,
        dk_line_kind="ou",
    )
    fd_quote = ResolvedSharpQuote(
        over_odds=-110,
        under_odds=-110,
        dk_line=22.5,
        betr_line=22.5,
        adjustment_method="fd_exact",
        corroborated=True,
        dk_main_line=22.5,
        dk_line_kind="ou",
    )

    weighted = _consensus_sharp_quote(
        betr_line=22.5,
        quotes=[("DraftKings", dk_quote), ("FanDuel", fd_quote)],
    )

    monkeypatch.setattr("config.settings.SHARP_BOOK_WEIGHTS_DK", 1.0)
    monkeypatch.setattr("config.settings.SHARP_BOOK_WEIGHTS_FD", 1.0)
    baseline = _consensus_sharp_quote(
        betr_line=22.5,
        quotes=[("DraftKings", dk_quote), ("FanDuel", fd_quote)],
    )

    assert weighted.over_odds != baseline.over_odds


def _espn(player: str, market: str, line: float, over: int, under: int, *, main=True) -> dict:
    return {
        "sportsbook": "ESPN",
        "player": player,
        "market": market,
        "line": line,
        "over_odds": over,
        "under_odds": under,
        "is_main_line": main,
        "event_start": _EVENT_START,
    }


def test_three_book_consensus_when_all_exact():
    betr = _betr("Test Player", "points", 22.5)
    dk_ladder = build_player_market_ladder(
        [_dk("Test Player", "points", 22.5, -130, 110, main=False)],
        normalize_player_name=normalize_player_name,
    )
    fd_ladder = build_player_market_ladder(
        [_fd("Test Player", "points", 22.5, -120, -110, main=False)],
        normalize_player_name=normalize_player_name,
    )
    espn_ladder = build_player_market_ladder(
        [_espn("Test Player", "points", 22.5, -125, -115, main=False)],
        normalize_player_name=normalize_player_name,
    )

    quote, reason = resolve_multi_book_sharp_quote(
        betr,
        dk_ladder,
        fd_ladder,
        normalize_player_name=normalize_player_name,
        espn_ou_ladder=espn_ladder,
    )

    assert reason is None
    assert quote is not None
    assert quote.adjustment_method == "multi_book_consensus"
    assert quote.sharp_books == ("DraftKings", "FanDuel", "ESPN")


def test_consensus_weights_espn_env_override(monkeypatch):
    monkeypatch.setattr("config.settings.SHARP_BOOK_WEIGHTS_DK", 1.0)
    monkeypatch.setattr("config.settings.SHARP_BOOK_WEIGHTS_FD", 1.0)
    monkeypatch.setattr("config.settings.SHARP_BOOK_WEIGHTS_ESPN", 3.0)

    quotes = [
        (
            "DraftKings",
            ResolvedSharpQuote(
                over_odds=-200,
                under_odds=170,
                dk_line=22.5,
                betr_line=22.5,
                adjustment_method="exact",
                corroborated=True,
                dk_main_line=22.5,
                dk_line_kind="ou",
            ),
        ),
        (
            "FanDuel",
            ResolvedSharpQuote(
                over_odds=-110,
                under_odds=-110,
                dk_line=22.5,
                betr_line=22.5,
                adjustment_method="fd_exact",
                corroborated=True,
                dk_main_line=22.5,
                dk_line_kind="ou",
            ),
        ),
        (
            "ESPN",
            ResolvedSharpQuote(
                over_odds=-105,
                under_odds=-115,
                dk_line=22.5,
                betr_line=22.5,
                adjustment_method="espn_exact",
                corroborated=True,
                dk_main_line=22.5,
                dk_line_kind="ou",
            ),
        ),
    ]
    weighted = _consensus_sharp_quote(betr_line=22.5, quotes=quotes)

    monkeypatch.setattr("config.settings.SHARP_BOOK_WEIGHTS_ESPN", 1.0)
    baseline = _consensus_sharp_quote(betr_line=22.5, quotes=quotes)

    assert weighted.over_odds != baseline.over_odds


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
    assert quote.adjustment_method == "dk_interpolated"
    assert quote.dk_over_odds is not None
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


def test_dk_ou_plus_fd_milestone_assembles_one_combo_quote():
    betr = _betr("Junior Perez", "h+r+rbi", 0.5)
    dk_ladder = build_player_market_ladder(
        [_dk("Junior Perez", "h+r+rbi", 0.5, -114, -117)],
        normalize_player_name=normalize_player_name,
    )
    fd_ladder = build_player_market_ladder([], normalize_player_name=normalize_player_name)
    fd_ms = build_milestone_ladders(
        [
            {
                "player": "Junior Perez",
                "market": "h+r+rbi",
                "line": 0.5,
                "line_kind": "milestone",
                "milestone_threshold": 1,
                "over_odds": -165,
                "sportsbook": "FanDuel",
            }
        ],
        normalize_player_name=normalize_player_name,
    )

    quote, reason = resolve_multi_book_sharp_quote(
        betr,
        dk_ladder,
        fd_ladder,
        normalize_player_name=normalize_player_name,
        fd_milestone_ladder=fd_ms.get("FanDuel"),
    )

    assert reason is None
    assert quote is not None
    assert quote.adjustment_method == "ou_ms_combo"
    assert quote.dk_over_odds == -114
    assert quote.dk_under_odds == -117
    assert quote.fd_over_odds == -165
    assert quote.fd_under_odds is None
    assert quote.fd_milestone_one_sided is True
    assert quote.over_odds == -114
    assert quote.under_odds == -117
