from core.engine import find_ev_opportunities, normalize_player_name
from core.line_adjustment import (
    build_milestone_ladder,
    build_player_market_ladder,
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
    assert quote.over_odds == 110


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


def test_find_ev_opportunities_uses_line_adjustment_for_mismatch():
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

    assert results
    assert results[0]["line_source"] == "dk_extrapolated"
    assert results[0]["betr_line"] == 28.5
    assert results[0]["dk_matched_line"] == 29.5
    assert results[0]["dk_quote_one_sided"] is False


def test_find_ev_opportunities_flags_milestone_quote():
    betr = [
        {
            "sportsbook": "Betr",
            "player": "Alex Caruso",
            "market": "steals",
            "line": 1.5,
            "over_odds": -120,
            "under_odds": -120,
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
            "over_odds": -250,
        }
    ]

    results = find_ev_opportunities(betr, dk, min_ev=0.0)

    assert results
    over_row = next(r for r in results if r["side"] == "over")
    assert over_row["line_source"] == "dk_milestone_exact"
    assert over_row["dk_quote_one_sided"] is True
    assert over_row["undisclosed_vig_caveat"] is True
    assert over_row["plus_ev"] is True
    assert over_row["plus_ev_milestone_caveat"] is True
    assert over_row["dk_under_odds"] is None
    assert over_row["dk_line_kind"] == "milestone"
