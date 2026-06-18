from core.ev_display import (
    format_ev_opportunity_row,
    format_ev_opportunities_table,
    format_ou_odds,
)


def test_format_ou_odds():
    assert format_ou_odds(110, -140) == "+110/-140"
    assert format_ou_odds(-110, -110) == "-110/-110"
    assert format_ou_odds(None, None) == "—"


def test_format_ev_opportunity_row_columns():
    row = {
        "player": "Shai Gilgeous-Alexander",
        "league": "nba",
        "side": "over",
        "market": "points",
        "line": 29.5,
        "side_hit_pct": 52.4,
        "ev_pct": 3.2,
        "dk_over_odds": -130,
        "dk_under_odds": 110,
        "fd_over_odds": -125,
        "fd_under_odds": 105,
        "line_source": "multi_book_consensus",
    }
    line = format_ev_opportunity_row(row)
    assert "Shai Gilgeous-A" in line
    assert "NBA" in line
    assert "OVER" in line
    assert "points" in line
    assert "29.5" in line
    assert "52.4%" in line
    assert "+3.2" in line
    assert "+110/-130" not in line
    assert "-130/+110" in line
    assert "-125/+105" in line
    assert "mb_cons" in line


def test_format_ev_opportunity_row_fd_only_shows_dk_dash():
    row = {
        "player": "Test Player",
        "league": "WNBA",
        "side": "under",
        "market": "rebounds",
        "line": 8.5,
        "side_hit_pct": 48.0,
        "dk_over_odds": None,
        "dk_under_odds": None,
        "fd_over_odds": 100,
        "fd_under_odds": -132,
        "line_source": "fd_alt",
    }
    line = format_ev_opportunity_row(row)
    assert "WNBA" in line
    assert "—" in line
    assert "+100/-132" in line
    assert "fd_alt" in line


def test_format_ev_opportunities_table_includes_header():
    table = format_ev_opportunities_table([])
    assert "Player" in table
    assert "Lg" in table
    assert "Hit%" in table
    assert "EV%" in table
    assert "+EV" not in table
    assert "DK" in table
    assert "FD" in table
    assert "Src" in table
    assert "Live" in table


def test_format_ev_opportunity_row_live_marker():
    row = {
        "player": "Francisco Lindor",
        "league": "MLB",
        "side": "over",
        "market": "hits",
        "line": 1.5,
        "side_hit_pct": 55.0,
        "dk_over_odds": -115,
        "dk_under_odds": -110,
        "is_live": True,
    }
    line = format_ev_opportunity_row(row)
    assert " L " in line or line.endswith(" L") or "| L" in line


def test_format_ev_opportunity_row_not_live_shows_dash():
    row = {
        "player": "Aaron Judge",
        "league": "MLB",
        "side": "over",
        "market": "hits",
        "line": 1.5,
        "side_hit_pct": 55.0,
        "dk_over_odds": -115,
        "dk_under_odds": -110,
        "is_live": False,
    }
    line = format_ev_opportunity_row(row)
    cells = [c.strip() for c in line.split("|")]
    live_cell = cells[-1]
    assert live_cell == "—"


def test_format_ev_opportunity_row_missing_league_shows_dash():
    row = {
        "player": "Test Player",
        "side": "over",
        "market": "points",
        "line": 10.5,
    }
    line = format_ev_opportunity_row(row)
    cells = [c.strip() for c in line.split("|")]
    assert cells[1] == "—"
