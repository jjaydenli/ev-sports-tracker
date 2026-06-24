from core.engine import find_ev_opportunities, normalize_player_name
from core.line_adjustment import (
    _extrapolate_fair_probs,
    _fair_probs_from_odds,
    build_milestone_ladder,
    build_player_market_ladder,
    is_ev_eligible_quote,
    resolve_sharp_quote,
)


def test_resolve_exact_line_on_alternate():
    ladder = build_player_market_ladder(
        [
            {
                "player": "Test Player",
                "market": "points",
                "line": 29.5,
                "over_odds": -111,
                "under_odds": -115,
                "is_main_line": True,
            },
            {
                "player": "Test Player",
                "market": "points",
                "line": 28.5,
                "over_odds": -105,
                "under_odds": -125,
                "is_main_line": False,
            },
        ],
        normalize_player_name=normalize_player_name,
    )
    betr = {
        "player": "Test Player",
        "market": "points",
        "line": 28.5,
        "over_odds": -120,
        "under_odds": -120,
    }

    quote, reason = resolve_sharp_quote(
        betr, ladder, normalize_player_name=normalize_player_name
    )

    assert reason is None
    assert quote is not None
    assert quote.adjustment_method == "dk_alt"
    assert quote.corroborated is True
    assert quote.over_odds == -105
    assert quote.dk_line_kind == "ou"


def test_resolve_extrapolates_when_only_main_line():
    ladder = build_player_market_ladder(
        [
            {
                "player": "Shai Gilgeous-Alexander",
                "market": "points",
                "line": 29.5,
                "over_odds": -145,
                "under_odds": 110,
                "is_main_line": True,
            },
        ],
        normalize_player_name=normalize_player_name,
    )
    betr = {
        "player": "Shai Gilgeous-Alexander",
        "market": "points",
        "line": 28.5,
        "over_odds": -120,
        "under_odds": -120,
    }

    quote, reason = resolve_sharp_quote(
        betr, ladder, normalize_player_name=normalize_player_name
    )

    assert reason is None
    assert quote is not None
    assert quote.adjustment_method == "dk_extrapolated"
    assert quote.corroborated is False
    assert quote.dk_line == 29.5
    assert quote.betr_line == 28.5


def test_resolve_milestone_exact_at_betr_line():
    ou_ladder = build_player_market_ladder([], normalize_player_name=normalize_player_name)
    milestone_ladder = build_milestone_ladder(
        [
            {
                "player": "Alex Caruso",
                "market": "steals",
                "line": 1.5,
                "line_kind": "milestone",
                "milestone_threshold": 2,
                "over_odds": 110,
                "is_main_line": True,
            },
        ],
        normalize_player_name=normalize_player_name,
    )
    betr = {
        "player": "Alex Caruso",
        "market": "steals",
        "line": 1.5,
        "over_odds": -120,
        "under_odds": -120,
    }

    quote, reason = resolve_sharp_quote(
        betr,
        ou_ladder,
        normalize_player_name=normalize_player_name,
        milestone_ladder=milestone_ladder,
    )

    assert reason is None
    assert quote is not None
    assert quote.adjustment_method == "dk_milestone_exact"
    assert quote.dk_line_kind == "milestone"
    assert quote.under_odds is None
    assert quote.dk_over_odds == 110
    assert quote.over_odds != 110
    assert quote.milestone_admitted is False


def test_ou_preferred_over_milestone_when_exact_ou_exists():
    ou_ladder = build_player_market_ladder(
        [
            {
                "player": "Alex Caruso",
                "market": "steals",
                "line": 1.5,
                "over_odds": -120,
                "under_odds": -110,
                "is_main_line": True,
            },
        ],
        normalize_player_name=normalize_player_name,
    )
    milestone_ladder = build_milestone_ladder(
        [
            {
                "player": "Alex Caruso",
                "market": "steals",
                "line": 1.5,
                "line_kind": "milestone",
                "milestone_threshold": 2,
                "over_odds": 110,
            },
        ],
        normalize_player_name=normalize_player_name,
    )
    betr = {
        "player": "Alex Caruso",
        "market": "steals",
        "line": 1.5,
        "over_odds": -120,
        "under_odds": -120,
    }

    quote, _ = resolve_sharp_quote(
        betr,
        ou_ladder,
        normalize_player_name=normalize_player_name,
        milestone_ladder=milestone_ladder,
    )

    assert quote is not None
    assert quote.adjustment_method == "exact"
    assert quote.dk_line_kind == "ou"


def test_milestone_fallback_when_ou_extrapolated():
    ou_ladder = build_player_market_ladder(
        [
            {
                "player": "Alex Caruso",
                "market": "steals",
                "line": 0.5,
                "over_odds": -200,
                "under_odds": 150,
                "is_main_line": True,
            },
        ],
        normalize_player_name=normalize_player_name,
    )
    milestone_ladder = build_milestone_ladder(
        [
            {
                "player": "Alex Caruso",
                "market": "steals",
                "line": 1.5,
                "line_kind": "milestone",
                "milestone_threshold": 2,
                "over_odds": 110,
                "is_main_line": True,
            },
        ],
        normalize_player_name=normalize_player_name,
    )
    betr = {
        "player": "Alex Caruso",
        "market": "steals",
        "line": 1.5,
        "over_odds": -120,
        "under_odds": -120,
    }

    quote, _ = resolve_sharp_quote(
        betr,
        ou_ladder,
        normalize_player_name=normalize_player_name,
        milestone_ladder=milestone_ladder,
    )

    assert quote is not None
    assert quote.adjustment_method == "dk_milestone_exact"
    assert quote.dk_line_kind == "milestone"


def test_find_ev_opportunities_skips_extrapolated_line_mismatch():
    betr = [
        {
            "sportsbook": "Betr",
            "player": "Shai Gilgeous-Alexander",
            "market": "points",
            "line": 28.5,
            "over_odds": -120,
            "under_odds": -120,
        }
    ]
    dk = [
        {
            "sportsbook": "DraftKings",
            "player": "Shai Gilgeous-Alexander",
            "market": "points",
            "line": 29.5,
            "over_odds": -145,
            "under_odds": 110,
            "is_main_line": True,
        }
    ]

    results = find_ev_opportunities(betr, dk, min_ev=0.0)

    assert results == []


def test_fox_points_extrapolated_resolves_but_not_ev_eligible():
    """De'Aaron Fox 13.5 under: DK scrape had 14.5 only (May 2026 audit)."""
    betr = {
        "player": "De'Aaron Fox",
        "market": "points",
        "line": 13.5,
        "over_odds": -120,
        "under_odds": -120,
    }
    ladder = build_player_market_ladder(
        [
            {
                "player": "De'Aaron Fox",
                "market": "points",
                "line": 14.5,
                "over_odds": -102,
                "under_odds": -124,
                "is_main_line": True,
            },
        ],
        normalize_player_name=normalize_player_name,
    )

    quote, reason = resolve_sharp_quote(
        betr, ladder, normalize_player_name=normalize_player_name
    )

    assert reason is None
    assert quote is not None
    assert quote.adjustment_method == "dk_extrapolated"
    assert not is_ev_eligible_quote(quote)

    dk_rows = [
        {
            "sportsbook": "DraftKings",
            "player": "De'Aaron Fox",
            "market": "points",
            "line": 14.5,
            "over_odds": -102,
            "under_odds": -124,
            "is_main_line": True,
        },
    ]
    assert find_ev_opportunities(
        [{"sportsbook": "Betr", **betr}], dk_rows, min_ev=0.0
    ) == []


def test_extrapolate_lower_line_increases_fair_over():
    fair_over, fair_under = _fair_probs_from_odds(-102, -124)
    lower_over, lower_under = _extrapolate_fair_probs(
        fair_over,
        fair_under,
        anchor_line=14.5,
        target_line=13.5,
        market="points",
    )
    assert lower_over > fair_over
    assert lower_under < fair_under


def test_find_ev_opportunities_skips_non_admitted_milestone_quote():
    betr = [
        {
            "sportsbook": "Betr",
            "player": "Alex Caruso",
            "market": "steals",
            "line": 1.5,
            "over_odds": -120,
            "under_odds": -120,
            "event_start": "2026-06-19T23:00:00.000Z",
        }
    ]
    dk = [
        {
            "sportsbook": "DraftKings",
            "player": "Alex Caruso",
            "market": "steals",
            "line": 1.5,
            "line_kind": "milestone",
            "milestone_threshold": 2,
            "over_odds": 110,
            "event_start": "2026-06-19T23:00:00.000Z",
        }
    ]

    results = find_ev_opportunities(betr, dk, min_ev=0.0)

    assert results == []


def test_ladder_row_carries_event_start():
    ladder = build_player_market_ladder(
        [
            {
                "player": "Test Player",
                "market": "points",
                "line": 20.5,
                "over_odds": -110,
                "under_odds": -110,
                "event_start": "2026-06-19T23:05:00.000Z",
            },
        ],
        normalize_player_name=normalize_player_name,
    )
    row = ladder["test player|points|2026-06-19T23"][20.5]
    assert row["event_start"] == "2026-06-19T23:05:00.000Z"


def test_resolved_quote_exposes_sharp_event_start():
    ladder = build_player_market_ladder(
        [
            {
                "player": "Test Player",
                "market": "points",
                "line": 20.5,
                "over_odds": -110,
                "under_odds": -110,
                "event_start": "2026-06-19T23:05:00.000Z",
            },
        ],
        normalize_player_name=normalize_player_name,
    )
    betr = {
        "player": "Test Player",
        "market": "points",
        "line": 20.5,
        "over_odds": -120,
        "under_odds": -120,
        "event_start": "2026-06-19T23:05:00.000Z",
    }
    quote, reason = resolve_sharp_quote(
        betr, ladder, normalize_player_name=normalize_player_name
    )
    assert reason is None
    assert quote is not None
    assert quote.sharp_event_start == "2026-06-19T23:05:00.000Z"


def _ou_row(player, line, over, under, *, event_start="2026-06-19T23:05:00.000Z"):
    return {
        "player": player,
        "market": "hits",
        "line": line,
        "over_odds": over,
        "under_odds": under,
        "event_start": event_start,
    }


def test_conflicting_collision_drops_pm_key_from_ladder():
    # Two distinct players collapse to one normalized name|market|hour key; their
    # same-line quotes conflict, so the whole key is dropped rather than silently
    # resolving to whichever row wrote last.
    ladder = build_player_market_ladder(
        [
            _ou_row("Will Smith", 0.5, -130, +110),
            _ou_row("Will Smith", 0.5, +140, -170),
        ],
        normalize_player_name=normalize_player_name,
    )
    assert "will smith|hits|2026-06-19T23" not in ladder

    betr = _ou_row("Will Smith", 0.5, -120, -120)
    quote, reason = resolve_sharp_quote(
        betr, ladder, normalize_player_name=normalize_player_name
    )
    assert quote is None
    assert reason == "no_dk_market"


def test_identical_odds_duplicate_keeps_matching():
    # A harmless duplicate (same odds) overwrites silently and still resolves.
    ladder = build_player_market_ladder(
        [
            _ou_row("Solo Player", 0.5, -120, -110),
            _ou_row("Solo Player", 0.5, -120, -110),
        ],
        normalize_player_name=normalize_player_name,
    )
    betr = _ou_row("Solo Player", 0.5, -130, -130)
    quote, reason = resolve_sharp_quote(
        betr, ladder, normalize_player_name=normalize_player_name
    )
    assert reason is None
    assert quote is not None
    assert quote.adjustment_method == "exact"
