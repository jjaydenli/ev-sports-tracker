"""o0.5 hits ↔ total_bases market equivalence at the per-book sharp filter."""

from config.market_maps import O05_EQUIVALENT_MARKETS, equivalent_o05_markets
from core.engine import (
    _filter_sharp_props_by_match_context,
    find_ev_opportunities,
    normalize_player_name,
)

_EVENT_START = "2026-06-19T23:00:00.000Z"
_GAME = "BAL@LAD"
_LEAGUE = "MLB"


def _betr(
    player: str,
    market: str,
    line: float,
    *,
    event_start: str = _EVENT_START,
    game: str = _GAME,
) -> dict:
    return {
        "sportsbook": "Betr",
        "player": player,
        "market": market,
        "line": line,
        "league": _LEAGUE,
        "game": game,
        "over_odds": -120,
        "under_odds": -120,
        "event_start": event_start,
    }


def _dk(
    player: str,
    market: str,
    line: float,
    over: int,
    under: int,
    *,
    event_start: str = _EVENT_START,
    game: str = _GAME,
    line_kind: str = "ou",
    milestone_threshold: int | None = None,
) -> dict:
    prop = {
        "sportsbook": "DraftKings",
        "player": player,
        "market": market,
        "line": line,
        "league": _LEAGUE,
        "game": game,
        "over_odds": over,
        "under_odds": under,
        "line_kind": line_kind,
        "event_start": event_start,
    }
    if milestone_threshold is not None:
        prop["milestone_threshold"] = milestone_threshold
    return prop


def _fd(
    player: str,
    market: str,
    line: float,
    over: int,
    under: int,
    *,
    event_start: str = _EVENT_START,
    game: str = _GAME,
) -> dict:
    return {
        "sportsbook": "FanDuel",
        "player": player,
        "market": market,
        "line": line,
        "league": _LEAGUE,
        "game": game,
        "over_odds": over,
        "under_odds": under,
        "event_start": event_start,
    }


def test_equivalent_o05_markets_returns_pair_for_hits_and_total_bases():
    assert equivalent_o05_markets("hits") == O05_EQUIVALENT_MARKETS
    assert equivalent_o05_markets("total_bases") == O05_EQUIVALENT_MARKETS
    assert equivalent_o05_markets("points") == frozenset({"points"})


def test_borrow_forward_hits_from_total_bases():
    """Betr hits o0.5 priced off DK total_bases o0.5 when hits is missing."""
    betr = [_betr("Freddie Freeman", "hits", 0.5)]
    dk = [_dk("Freddie Freeman", "total_bases", 0.5, -140, 120)]

    results = find_ev_opportunities(betr, dk, min_ev=0.0)

    assert results
    assert results[0]["market"] == "hits"
    assert results[0]["dk_over_odds"] == -140


def test_borrow_reverse_total_bases_from_hits():
    """Betr total_bases o0.5 priced off DK hits o0.5 when total_bases is missing."""
    betr = [_betr("Freddie Freeman", "total_bases", 0.5)]
    dk = [_dk("Freddie Freeman", "hits", 0.5, -135, 115)]

    results = find_ev_opportunities(betr, dk, min_ev=0.0)

    assert results
    assert results[0]["market"] == "total_bases"
    assert results[0]["dk_over_odds"] == -135


def test_prefer_native_skips_borrow_when_both_markets_present():
    """When DK has native hits o0.5, do not also borrow total_bases o0.5."""
    betr = _betr("Freddie Freeman", "hits", 0.5)
    dk_props = [
        _dk("Freddie Freeman", "hits", 0.5, -110, -110),
        _dk("Freddie Freeman", "total_bases", 0.5, -140, -140),
    ]

    filtered = _filter_sharp_props_by_match_context(betr, dk_props)

    assert len(filtered) == 1
    assert filtered[0]["market"] == "hits"
    assert filtered[0]["over_odds"] == -110

    results = find_ev_opportunities([betr], dk_props, min_ev=0.0)
    assert results
    assert results[0]["dk_over_odds"] == -110


def test_cross_book_corroboration_dk_hits_fd_total_bases():
    """DK native hits o0.5 + FD borrowed total_bases o0.5 compose multi-book consensus."""
    betr = [_betr("Freddie Freeman", "hits", 0.5)]
    dk = [_dk("Freddie Freeman", "hits", 0.5, -130, 110)]
    fd = [_fd("Freddie Freeman", "total_bases", 0.5, -120, -110)]

    results = find_ev_opportunities(betr, dk, fanduel_props=fd, min_ev=0.0)

    assert results
    assert results[0]["line_source"] == "multi_book_consensus"
    assert results[0]["dk_over_odds"] == -130
    assert results[0]["fd_over_odds"] == -120
    assert set(results[0]["sharp_books"]) == {"DraftKings", "FanDuel"}


def test_line_gating_no_borrow_at_non_half_line():
    """Equivalence applies only at 0.5; 1.5 lines do not cross-map."""
    betr = [_betr("Freddie Freeman", "hits", 1.5)]
    dk = [_dk("Freddie Freeman", "total_bases", 1.5, -110, -110)]

    assert find_ev_opportunities(betr, dk, min_ev=0.0) == []


def test_no_milestone_borrow_for_o05():
    """Milestone hits rows are not borrowed as o/u equivalents."""
    betr = [_betr("Freddie Freeman", "total_bases", 0.5)]
    dk = [
        _dk(
            "Freddie Freeman",
            "hits",
            0.5,
            -220,
            None,
            line_kind="milestone",
            milestone_threshold=1,
        )
    ]

    assert find_ev_opportunities(betr, dk, min_ev=0.0) == []


def test_context_required_no_borrow_on_event_hour_mismatch():
    betr = [_betr("Freddie Freeman", "hits", 0.5, event_start="2026-06-19T17:05:00.000Z")]
    dk = [
        _dk(
            "Freddie Freeman",
            "total_bases",
            0.5,
            -110,
            -110,
            event_start="2026-06-19T23:10:00.000Z",
        )
    ]

    assert find_ev_opportunities(betr, dk, min_ev=0.0) == []


def test_context_required_no_borrow_on_game_mismatch():
    betr = [_betr("Freddie Freeman", "hits", 0.5, game="BAL@LAD")]
    dk = [_dk("Freddie Freeman", "total_bases", 0.5, -110, -110, game="NYY@BOS")]

    filtered = _filter_sharp_props_by_match_context(betr[0], dk)
    assert filtered == []
