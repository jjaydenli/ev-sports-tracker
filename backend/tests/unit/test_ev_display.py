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
        "side": "over",
        "market": "points",
        "line": 29.5,
        "side_hit_pct": 52.4,
        "dk_over_odds": -130,
        "dk_under_odds": 110,
        "fd_over_odds": -125,
        "fd_under_odds": 105,
        "line_source": "multi_book_consensus",
    }
    line = format_ev_opportunity_row(row)
    assert "Shai Gilgeous-Alexa" in line
    assert "OVER" in line
    assert "points" in line
    assert "29.5" in line
    assert "52.4%" in line
    assert "+110/-130" not in line
    assert "-130/+110" in line
    assert "-125/+105" in line
    assert "mb_consensus" in line


def test_format_ev_opportunity_row_fd_only_shows_dk_dash():
    row = {
        "player": "Test Player",
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
    assert "—" in line
    assert "+100/-132" in line
    assert "fd_alt" in line


def test_format_ev_opportunities_table_includes_header():
    table = format_ev_opportunities_table([])
    assert "Player" in table
    assert "Hit%" in table
    assert "DK" in table
    assert "FD" in table
    assert "Src" in table
