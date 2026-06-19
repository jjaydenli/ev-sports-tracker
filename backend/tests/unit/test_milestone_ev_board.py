import json
from pathlib import Path

import pytest

from config.settings import MILESTONE_ASSUMED_HOLD, MILESTONE_MIN_FAIR_OVER
from core.engine import find_ev_opportunities, normalize_player_name
from core.ev_display import format_ev_opportunity_row
from core.line_adjustment import (
    build_milestone_ladder,
    build_player_market_ladder,
    devig_milestone_fair_over,
    estimate_ou_hold,
    is_ev_eligible_quote,
    resolve_sharp_quote,
)
from utils.math_utils import american_to_implied, implied_to_american

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "dk_milestone_ladder.json"


@pytest.fixture
def milestone_fixture() -> dict:
    return json.loads(_FIXTURE.read_text())


def _lindor_ou_ladder(fixture: dict) -> dict:
    props = [
        {
            "player": fixture["player"],
            "market": fixture["market"],
            "line": row["line"],
            "over_odds": row["over_odds"],
            "under_odds": row["under_odds"],
            "is_main_line": row["is_main_line"],
            "sportsbook": "DraftKings",
        }
        for row in fixture["ou_rows"]
    ]
    return {"DraftKings": build_player_market_ladder(props, normalize_player_name=normalize_player_name)}


def _lindor_milestone_ladder(fixture: dict) -> dict:
    props = [
        {
            "player": fixture["player"],
            "market": fixture["market"],
            "line": row["line"],
            "line_kind": "milestone",
            "milestone_threshold": row["milestone_threshold"],
            "over_odds": row["over_odds"],
            "is_main_line": row["is_main_line"],
            "sportsbook": "DraftKings",
        }
        for row in fixture["milestone_ladder"]
    ]
    return build_milestone_ladder(props, normalize_player_name=normalize_player_name)


def test_estimate_ou_hold_returns_average(milestone_fixture):
    ou_ladders = _lindor_ou_ladder(milestone_fixture)
    pm_key = f"{normalize_player_name(milestone_fixture['player'])}|{milestone_fixture['market']}"
    hold = estimate_ou_hold(ou_ladders, pm_key, preferred_book="DraftKings")
    assert hold is not None
    assert hold > 0


def test_estimate_ou_hold_none_without_ou_rows():
    assert estimate_ou_hold({}, "missing|hits") is None


def test_devig_milestone_ladder_normalized_devigs_ladder(milestone_fixture):
    ladder = _lindor_milestone_ladder(milestone_fixture)
    pm_key = f"{normalize_player_name(milestone_fixture['player'])}|{milestone_fixture['market']}"
    lines = ladder[pm_key]
    ou_ladders = _lindor_ou_ladder(milestone_fixture)
    hold = estimate_ou_hold(ou_ladders, pm_key, preferred_book="DraftKings")

    fair_mid, method_mid = devig_milestone_fair_over(
        lines, 1.5, market="hits", ou_hold=hold
    )
    hold_shrink_mid, method_hold = devig_milestone_fair_over(
        {1.5: lines[1.5]}, 1.5, market="hits", ou_hold=hold
    )
    assert method_mid == "ladder_normalized"
    assert method_hold == "hold_shrink"
    assert fair_mid != pytest.approx(hold_shrink_mid)
    assert 0 < fair_mid < 1


def test_devig_milestone_hold_shrink_uses_observed_hold(milestone_fixture):
    lone = milestone_fixture["lone_milestone"]
    lines = {
        lone["line"]: {
            "over_odds": lone["over_odds"],
            "milestone_threshold": lone["milestone_threshold"],
            "is_main_line": True,
            "sportsbook": "DraftKings",
        }
    }
    ou_ladders = _lindor_ou_ladder(milestone_fixture)
    pm_key = f"{normalize_player_name(milestone_fixture['player'])}|{milestone_fixture['market']}"
    hold = estimate_ou_hold(ou_ladders, pm_key, preferred_book="DraftKings")
    raw = american_to_implied(lone["over_odds"])
    fair_over, method = devig_milestone_fair_over(
        lines, lone["line"], market="hits", ou_hold=hold
    )
    assert method == "hold_shrink"
    assert fair_over == pytest.approx(raw * (1.0 - hold / 2.0))


def test_devig_milestone_hold_shrink_fallback_assumed_hold(milestone_fixture):
    lone = milestone_fixture["lone_milestone"]
    lines = {
        lone["line"]: {
            "over_odds": lone["over_odds"],
            "milestone_threshold": lone["milestone_threshold"],
            "is_main_line": True,
            "sportsbook": "DraftKings",
        }
    }
    raw = american_to_implied(lone["over_odds"])
    fair_over, method = devig_milestone_fair_over(
        lines, lone["line"], market="hits", ou_hold=None
    )
    assert method == "hold_shrink"
    assert fair_over == pytest.approx(raw * (1.0 - MILESTONE_ASSUMED_HOLD / 2.0))


def test_milestone_admitted_gate_boundary():
    above_input = MILESTONE_MIN_FAIR_OVER / (1.0 - MILESTONE_ASSUMED_HOLD / 2.0) + 0.001
    lines = {
        0.5: {
            "over_odds": implied_to_american(above_input),
            "milestone_threshold": 1,
            "is_main_line": True,
            "sportsbook": "DraftKings",
        }
    }
    fair_over, _ = devig_milestone_fair_over(lines, 0.5, market="hits", ou_hold=None)
    assert fair_over >= MILESTONE_MIN_FAIR_OVER

    soft_lines = {
        0.5: {
            "over_odds": implied_to_american(MILESTONE_MIN_FAIR_OVER - 0.05),
            "milestone_threshold": 1,
            "is_main_line": True,
            "sportsbook": "DraftKings",
        }
    }
    soft_fair, _ = devig_milestone_fair_over(soft_lines, 0.5, market="hits", ou_hold=None)
    assert soft_fair < MILESTONE_MIN_FAIR_OVER


def test_is_ev_eligible_milestone_exact_admitted():
    from core.line_adjustment import ResolvedSharpQuote

    admitted = ResolvedSharpQuote(
        over_odds=-200,
        under_odds=None,
        dk_line=0.5,
        betr_line=0.5,
        adjustment_method="dk_milestone_exact",
        corroborated=False,
        dk_main_line=0.5,
        dk_line_kind="milestone",
        milestone_admitted=True,
        milestone_devig_method="hold_shrink",
    )
    assert is_ev_eligible_quote(admitted)

    rejected = ResolvedSharpQuote(
        over_odds=110,
        under_odds=None,
        dk_line=0.5,
        betr_line=0.5,
        adjustment_method="dk_milestone_exact",
        corroborated=False,
        dk_main_line=0.5,
        dk_line_kind="milestone",
        milestone_admitted=False,
    )
    assert not is_ev_eligible_quote(rejected)

    interpolated = ResolvedSharpQuote(
        over_odds=-200,
        under_odds=None,
        dk_line=1.0,
        betr_line=1.0,
        adjustment_method="dk_milestone_interpolated",
        corroborated=False,
        dk_main_line=0.5,
        dk_line_kind="milestone",
        milestone_admitted=True,
    )
    assert not is_ev_eligible_quote(interpolated)


def test_ou_preferred_over_milestone_precedence(milestone_fixture):
    ou_ladder = build_player_market_ladder(
        [
            {
                "player": milestone_fixture["player"],
                "market": milestone_fixture["market"],
                "line": 1.5,
                "over_odds": -120,
                "under_odds": -110,
                "is_main_line": True,
            }
        ],
        normalize_player_name=normalize_player_name,
    )
    milestone_ladder = _lindor_milestone_ladder(milestone_fixture)
    betr = {
        "player": milestone_fixture["player"],
        "market": milestone_fixture["market"],
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


def test_find_ev_opportunities_admits_sharp_milestone(milestone_fixture):
    betr = [
        {
            "sportsbook": "Betr",
            "player": milestone_fixture["player"],
            "market": milestone_fixture["market"],
            "line": 0.5,
            "over_odds": -120,
            "under_odds": -120,
        }
    ]
    dk = [
        {
            "sportsbook": "DraftKings",
            "player": milestone_fixture["player"],
            "market": milestone_fixture["market"],
            "line": row["line"],
            "line_kind": "milestone",
            "milestone_threshold": row["milestone_threshold"],
            "over_odds": row["over_odds"],
            "is_main_line": row["is_main_line"],
        }
        for row in milestone_fixture["milestone_ladder"]
    ]
    results = find_ev_opportunities(betr, dk, min_ev=0.0)
    over_rows = [row for row in results if row["side"] == "over"]
    assert over_rows
    row = over_rows[0]
    assert row["milestone_admitted"] is True
    assert row["milestone_devig_method"] in {"ladder_normalized", "hold_shrink"}
    assert row["not_true_devig"] is True
    assert row["undisclosed_vig_caveat"] is True
    assert row["sharp_books"] == ["DraftKings"]


def test_find_ev_opportunities_skips_non_admitted_milestone():
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
            "over_odds": 110,
        }
    ]
    assert find_ev_opportunities(betr, dk, min_ev=0.0) == []


def test_non_dk_milestone_sets_sharp_books():
    ou_ladder = build_player_market_ladder([], normalize_player_name=normalize_player_name)
    milestone_ladder = build_milestone_ladder(
        [
            {
                "player": "Test Player",
                "market": "hits",
                "line": 0.5,
                "line_kind": "milestone",
                "milestone_threshold": 1,
                "over_odds": -220,
                "sportsbook": "FutureBook",
            }
        ],
        normalize_player_name=normalize_player_name,
    )
    betr = {
        "player": "Test Player",
        "market": "hits",
        "line": 0.5,
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
    assert quote.sharp_books == ("FutureBook",)
    assert quote.milestone_admitted is True


def test_cli_renders_milestone_src_badge():
    row = {
        "player": "Francisco Lindor",
        "league": "MLB",
        "side": "over",
        "market": "hits",
        "line": 0.5,
        "side_hit_pct": 68.0,
        "ev_pct": 4.5,
        "dk_over_odds": -200,
        "dk_under_odds": None,
        "line_source": "dk_milestone_exact",
    }
    line = format_ev_opportunity_row(row)
    assert "ms🔶" in line
