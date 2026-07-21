import re

import pytest

from config.team_abbrev import TEAM_ABBR_ALIASES, TEAM_FULL_NAME_TO_ABBR
from core.ev_display import (
    _EV_CELL_INDEX,
    _SRC_ADJ_METHODS,
    _SRC_EXACT_METHODS,
    _STACK_CELL_INDEX,
    _TEAM_CLUSTER_COLOR_BANK,
    EV_TABLE_HEADERS,
    EV_TABLE_WIDTHS,
    MARKET_ABBREV,
    _display_width,
    _ev_tier_color_code,
    _format_game,
    format_ev_opportunities_table,
    format_ev_opportunity_row,
    format_ev_table_header,
    format_ou_odds,
)
from core.line_adjustment import EV_ELIGIBLE_ADJUSTMENT_METHODS


def _cell_by_header(line: str, header: str) -> str:
    """Column value by header name, so tests survive a column reorder."""
    return line.split(" | ")[EV_TABLE_HEADERS.index(header)].strip()


def _stack_cell_ansi_code(line: str) -> int | None:
    cell = line.split(" | ")[_STACK_CELL_INDEX]
    match = re.search(r"\033\[38;5;(\d+)m", cell)
    return int(match.group(1)) if match else None


def test_format_ou_odds():
    assert format_ou_odds(110, -140) == "+110/-140"
    assert format_ou_odds(-110, -110) == "-110/-110"
    assert format_ou_odds(None, None) == "—"
    assert format_ou_odds(-165, None, milestone_one_sided=True) == "-165/🔶"


def _assert_row_column_widths(line: str) -> None:
    cells = line.split(" | ")
    assert len(cells) == len(EV_TABLE_WIDTHS)
    for cell, width in zip(cells, EV_TABLE_WIDTHS, strict=True):
        assert _display_width(cell) == width


def test_headers_and_widths_stay_in_lockstep():
    assert len(EV_TABLE_HEADERS) == len(EV_TABLE_WIDTHS)


def test_every_column_header_fits_its_own_width():
    """A header wider than its column ellipsizes into meaninglessness (e.g. 'Stac…')."""
    for header, width in zip(EV_TABLE_HEADERS, EV_TABLE_WIDTHS, strict=True):
        assert _display_width(header) <= width, f"header {header!r} overflows width {width}"


@pytest.mark.parametrize("market,abbrev", sorted(MARKET_ABBREV.items()))
def test_market_abbrev_fits_the_stat_column(market, abbrev):
    stat_width = EV_TABLE_WIDTHS[EV_TABLE_HEADERS.index("Stat")]
    assert _display_width(abbrev) <= stat_width, f"{market}->{abbrev} overflows Stat"


def test_market_abbrev_labels_are_unique():
    """Two markets sharing a label are indistinguishable on the board."""
    seen: dict[str, str] = {}
    for market, abbrev in MARKET_ABBREV.items():
        assert abbrev not in seen, f"{market} and {seen[abbrev]} both render {abbrev!r}"
        seen[abbrev] = market


# A Stat label equal to a team code is ambiguous against the Game column — "[TB]@NYY | ▲ | TB".
# Allowlisted only when the stat and the team can never share a row, i.e. different sports.
_BENIGN_TEAM_CODE_COLLISIONS = {
    "steals": "basketball-only stat; STL is the MLB Cardinals",
}


def test_market_abbrev_does_not_collide_with_team_codes():
    teams = set(TEAM_FULL_NAME_TO_ABBR.values()) | set(TEAM_ABBR_ALIASES)
    collisions = {m for m, a in MARKET_ABBREV.items() if a in teams}
    unexpected = collisions - set(_BENIGN_TEAM_CODE_COLLISIONS)
    assert not unexpected, (
        f"{unexpected} render as team codes; spell them out (as total_bases->BASES) "
        f"or allowlist with a reason if the stat and team cannot share a row"
    )


def test_milestone_reference_odds_render_beside_a_two_sided_src():
    """A book's one-sided milestone shows 🔶 in its own column without claiming the Src."""
    row = {
        "player": "Junior Perez",
        "league": "MLB",
        "game": "CIN@NYY",
        "team": "CIN",
        "side": "over",
        "market": "h+r+rbi",
        "line": 0.5,
        "fd_over_odds": -165,
        "fd_under_odds": None,
        "fd_milestone_one_sided": True,
        "line_source": "fd_exact",
    }
    line = format_ev_opportunity_row(row)
    assert _cell_by_header(line, "FD") == "-165/🔶"
    assert _cell_by_header(line, "Src") == "exact"
    _assert_row_column_widths(line)


def _src_for(line_source: str, **extra) -> str:
    row = {"player": "P", "league": "MLB", "side": "over", "market": "hits",
           "line": 1.5, "line_source": line_source, **extra}
    return _cell_by_header(format_ev_opportunity_row(row), "Src")


# The complete Src vocabulary. Anything outside this is a leak of engine internals.
_SRC_LABEL_RE = re.compile(r"^(exact(·\d+)?|ms🔶|adj|\?)$")

# Methods the engine can rank. Derived from the engine's own constant rather than restated
# here, so a newly-eligible method is covered the moment it is added — the point of the tests
# below is to fail until it is deliberately given a Src label.
_RANKABLE_METHODS = sorted(EV_ELIGIBLE_ADJUSTMENT_METHODS | {"milestone_exact"})


@pytest.mark.parametrize("method", _RANKABLE_METHODS)
def test_src_maps_every_rankable_method_to_a_real_label(method):
    """A method the engine can rank must never fall through to the unknown placeholder."""
    label = _src_for(method, sharp_books=["DraftKings", "FanDuel"])
    assert label != "?", f"{method} is EV-eligible but has no Src mapping"
    assert _SRC_LABEL_RE.match(label), f"{method} rendered {label!r}, not a known Src label"


@pytest.mark.parametrize("method", sorted(_SRC_EXACT_METHODS))
def test_src_exact_family_collapses_book_and_alt_identity(method):
    """Book identity and main-vs-alt are trust-neutral; they live in board.json."""
    assert _src_for(method) == "exact"


@pytest.mark.parametrize("method", sorted(_SRC_ADJ_METHODS))
def test_src_adjusted_family_collapses_to_quiet_umbrella(method):
    assert _src_for(method) == "adj"


def test_src_milestone_only_is_marked_inferred():
    assert _src_for("milestone_exact") == "ms🔶"


def test_src_never_leaks_a_raw_method_string():
    assert _src_for("some_future_method") == "?"


@pytest.mark.parametrize("n", [2, 3, 5])
def test_src_consensus_counts_corroborating_books(n):
    books = [f"Book{i}" for i in range(n)]
    assert _src_for("multi_book_consensus", sharp_books=books) == f"exact·{n}"


def test_src_consensus_of_one_reads_as_exact():
    """'cons·1' would be awkward; a lone book is just an exact quote."""
    assert _src_for("multi_book_consensus", sharp_books=["DraftKings"]) == "exact"


def test_src_labels_all_fit_the_column():
    """Src is sized to the longest label; a wider one would ellipsize."""
    src_width = EV_TABLE_WIDTHS[EV_TABLE_HEADERS.index("Src")]
    labels = [_src_for(m, sharp_books=["a", "b", "c"]) for m in _RANKABLE_METHODS]
    labels.append(_src_for("unmapped"))
    for label in labels:
        assert _display_width(label) <= src_width, f"{label!r} overflows Src"


def test_format_game_brackets_player_team():
    assert _format_game("CIN@NYY", "CIN") == "[CIN]@NYY"
    assert _format_game("CIN@NYY", "NYY") == "CIN@[NYY]"
    assert _format_game("NY@CLE", "NY") == "[NY]@CLE"
    assert _format_game(None, "CIN") == "—"
    assert _format_game("CIN@NYY", None) == "CIN@NYY"


def test_format_ev_opportunity_row_columns():
    row = {
        "player": "Shai Gilgeous-Alexander",
        "league": "nba",
        "game": "OKC@DAL",
        "team": "OKC",
        "side": "over",
        "market": "points",
        "line": 29.5,
        "side_hit_pct": 52.4,
        "ev_pct": 3.2,
        "dk_over_odds": -130,
        "dk_under_odds": 110,
        "fd_over_odds": -125,
        "fd_under_odds": 105,
        "espn_over_odds": -140,
        "espn_under_odds": 105,
        "line_source": "multi_book_consensus",
        "sharp_books": ["DraftKings", "FanDuel", "ESPN"],
    }
    line = format_ev_opportunity_row(row)
    assert "Shai Gilgeous-A" in line
    assert "NBA" in line
    assert _cell_by_header(line, "Side") == "▲"
    assert _cell_by_header(line, "Stat") == "PTS"
    assert "29.5" in line
    assert "52.4%" in line
    assert "+3.2" in line
    assert "+110/-130" not in line
    assert "-130/+110" in line
    assert "-125/+105" in line
    assert "-140/+105" in line
    assert _cell_by_header(line, "Src") == "exact·3"
    _assert_row_column_widths(line)


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
    assert _cell_by_header(line, "Src") == "exact"
    assert _cell_by_header(line, "Side") == "▼"


def test_format_ev_table_header_column_widths():
    from core.ev_display import format_ev_table_header

    _assert_row_column_widths(format_ev_table_header())


def test_format_ev_opportunities_table_includes_header():
    table = format_ev_opportunities_table([])
    assert "Player" in table
    assert "Lg" in table
    assert "Game" in table
    assert "Hit%" in table
    assert "EV%" in table
    assert "+EV" not in table
    assert "DK" in table
    assert "FD" in table
    assert "ESPN" in table
    assert "Src" in table
    assert "Live" in table
    # The stack column's header is the marker itself: it holds the column at marker width
    # and previews the glyph, so no header word is needed.
    assert table.splitlines()[0].split(" | ")[_STACK_CELL_INDEX] == "▌"


def test_table_header_is_ansi_free():
    """Non-terminal consumers read this verbatim; the header must carry no colour."""
    assert "\033[" not in format_ev_table_header()


def test_format_ev_opportunities_table_default_matches_plain_rows():
    """ev_pipeline call site: no highlight kwarg → byte-for-byte identical to plain rows."""
    row = {
        "player": "Aaron Judge",
        "league": "MLB",
        "game": "NYY@BOS",
        "team": "NYY",
        "side": "over",
        "market": "hits",
        "line": 1.5,
        "side_hit_pct": 55.0,
        "ev_pct": 2.1,
        "dk_over_odds": -115,
        "dk_under_odds": -110,
    }
    plain = format_ev_opportunities_table([row])
    assert plain == format_ev_table_header() + "\n" + "-" * len(format_ev_table_header()) + "\n" + format_ev_opportunity_row(row)


def test_format_ev_opportunities_table_highlight_per_cell():
    row = {
        "player": "Aaron Judge",
        "league": "MLB",
        "side": "over",
        "market": "hits",
        "line": 1.5,
        "ev_pct": 2.1,
    }
    table = format_ev_opportunities_table([row], highlight=lambda r: True)
    body_line = table.splitlines()[2]
    for cell in body_line.split(" | "):
        assert cell.startswith("\033[1;33m")
        assert cell.endswith("\033[0m")


def test_format_ev_opportunities_table_highlight_skips_when_false():
    row = {
        "player": "Aaron Judge",
        "league": "MLB",
        "side": "over",
        "market": "hits",
        "line": 1.5,
        "ev_pct": 2.1,
    }
    table = format_ev_opportunities_table([row], highlight=lambda r: False)
    body_line = table.splitlines()[2]
    assert "\033[" not in body_line


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
    assert _cell_by_header(line, "Live") == "—"


def test_format_ev_opportunity_row_missing_league_shows_dash():
    row = {
        "player": "Test Player",
        "side": "over",
        "market": "points",
        "line": 10.5,
    }
    line = format_ev_opportunity_row(row)
    assert _cell_by_header(line, "Lg") == "—"
    assert _cell_by_header(line, "Game") == "—"


def _row(player, *, team, league="MLB", market="hits", line=1.5, ev=0.05, ev_pct=5.0):
    return {
        "player": player,
        "league": league,
        "team": team,
        "side": "over",
        "market": market,
        "line": line,
        "ev": ev,
        "ev_pct": ev_pct,
    }


def test_team_cluster_marker_best_prop_per_player():
    rows = [
        _row("Player A", team="NYY", market="hits", ev=0.08, ev_pct=8.0),
        _row("Player A", team="NYY", market="runs", line=0.5, ev=0.03, ev_pct=3.0),
        _row("Player B", team="NYY", market="hits", ev=0.06, ev_pct=6.0),
        _row("Player B", team="NYY", market="rbis", line=0.5, ev=0.04, ev_pct=4.0),
    ]
    table = format_ev_opportunities_table(rows)
    body = table.splitlines()[2:]
    assert "▌" in body[0]
    assert "▌" not in body[1]
    assert "▌" in body[2]
    assert "▌" not in body[3]


def test_team_cluster_marker_lone_player_multiple_props_unmarked():
    rows = [
        _row("Solo Star", team="NYY", market="hits", ev=0.08),
        _row("Solo Star", team="NYY", market="runs", line=0.5, ev=0.03),
    ]
    table = format_ev_opportunities_table(rows)
    for line in table.splitlines()[2:]:
        assert "▌" not in line


def test_team_cluster_marker_cross_league_abbrev_no_false_positive():
    rows = [
        _row("Twins Player", team="MIN", league="MLB", ev=0.05),
        _row("Lynx Player", team="MIN", league="WNBA", ev=0.04),
    ]
    table = format_ev_opportunities_table(rows)
    for line in table.splitlines()[2:]:
        assert "▌" not in line


def test_team_cluster_marker_ev_tie_first_row_wins():
    rows = [
        _row("Player A", team="NYY", market="hits", ev=0.05),
        _row("Player A", team="NYY", market="runs", line=0.5, ev=0.05),
        _row("Player B", team="NYY", market="hits", ev=0.04),
    ]
    table = format_ev_opportunities_table(rows)
    body = table.splitlines()[2:]
    assert "▌" in body[0]
    assert "▌" not in body[1]
    assert "▌" in body[2]


def test_ev_tier_color_code_boundaries():
    cases = [
        (5.0, 46),
        (4.99, 40),
        (3.0, 40),
        (2.99, 34),
        (1.5, 34),
        (1.49, 28),
        (0.0, 28),
        (-0.01, 217),
        (-1.0, 217),
        (-1.01, 210),
        (-2.0, 210),
        (-2.01, 196),
    ]
    for ev_pct, expected in cases:
        assert _ev_tier_color_code(ev_pct) == expected


def test_format_ev_opportunity_row_color_ev_tier_ansi():
    row = {
        "player": "Test",
        "league": "MLB",
        "side": "over",
        "market": "hits",
        "line": 1.5,
        "ev_pct": 4.99,
    }
    line = format_ev_opportunity_row(row, color_ev=True)
    ev_cell = line.split(" | ")[_EV_CELL_INDEX]
    assert ev_cell.startswith("\033[38;5;40m")
    assert ev_cell.endswith("\033[0m")


def test_format_ev_opportunity_row_color_ev_skips_missing_ev_pct():
    row = {
        "player": "Test",
        "side": "over",
        "market": "hits",
        "line": 1.5,
    }
    line = format_ev_opportunity_row(row, color_ev=True)
    assert "\033[38;5;" not in line


def test_highlight_and_color_ev_combined_preserves_row_highlight():
    row = {
        "player": "Aaron Judge",
        "league": "MLB",
        "side": "over",
        "market": "hits",
        "line": 1.5,
        "ev_pct": 3.2,
        "dk_over_odds": -115,
        "dk_under_odds": -110,
    }
    table = format_ev_opportunities_table(
        [row],
        highlight=lambda r: True,
        color_ev=True,
    )
    cells = table.splitlines()[2].split(" | ")
    assert cells[_EV_CELL_INDEX].startswith("\033[1;38;5;40m")
    assert cells[_EV_CELL_INDEX - 1].startswith("\033[1;33m")
    assert cells[_EV_CELL_INDEX + 1].startswith("\033[1;33m")


def test_team_cluster_colors_distinct_teams():
    rows = [
        _row("Player A", team="NYY", ev=0.10),
        _row("Player B", team="NYY", ev=0.09),
        _row("Player C", team="LAD", ev=0.08),
        _row("Player D", team="LAD", ev=0.07),
    ]
    table = format_ev_opportunities_table(rows, color_ev=True)
    codes = {_stack_cell_ansi_code(line) for line in table.splitlines()[2:] if "▌" in line}
    assert codes == {_TEAM_CLUSTER_COLOR_BANK[0], _TEAM_CLUSTER_COLOR_BANK[1]}


def test_team_cluster_colors_same_team_shares_color():
    rows = [
        _row("Player A", team="NYY", market="hits", ev=0.08),
        _row("Player A", team="NYY", market="runs", line=0.5, ev=0.03),
        _row("Player B", team="NYY", ev=0.06),
    ]
    table = format_ev_opportunities_table(rows, color_ev=True)
    codes = [_stack_cell_ansi_code(line) for line in table.splitlines()[2:] if "▌" in line]
    assert len(codes) == 2
    assert codes[0] == codes[1] == _TEAM_CLUSTER_COLOR_BANK[0]


def test_team_cluster_colors_first_appearance_order():
    rows = [
        _row("LAD-1", team="LAD", ev=0.10),
        _row("LAD-2", team="LAD", ev=0.09),
        _row("NYY-1", team="NYY", ev=0.08),
        _row("NYY-2", team="NYY", ev=0.07),
    ]
    table = format_ev_opportunities_table(rows, color_ev=True)
    by_team: dict[str, int] = {}
    for line in table.splitlines()[2:]:
        if "▌" not in line:
            continue
        if "LAD" in line.split(" | ")[0]:
            by_team.setdefault("LAD", _stack_cell_ansi_code(line))
        elif "NYY" in line.split(" | ")[0]:
            by_team.setdefault("NYY", _stack_cell_ansi_code(line))
    assert by_team["LAD"] == _TEAM_CLUSTER_COLOR_BANK[0]
    assert by_team["NYY"] == _TEAM_CLUSTER_COLOR_BANK[1]


def test_team_cluster_colors_cycle_beyond_bank():
    teams = ["NYY", "LAD", "BOS", "HOU", "SF", "ATL", "CHC"]
    rows = []
    for team in teams:
        rows.append(_row(f"P1-{team}", team=team, ev=0.10))
        rows.append(_row(f"P2-{team}", team=team, ev=0.09))
    table = format_ev_opportunities_table(rows, color_ev=True)
    first_color_by_team: dict[str, int] = {}
    for line in table.splitlines()[2:]:
        if "▌" not in line:
            continue
        player = line.split(" | ")[0].strip()
        team = player.split("-", 1)[1]
        code = _stack_cell_ansi_code(line)
        assert code is not None
        first_color_by_team.setdefault(team, code)
    ordered = [first_color_by_team[t] for t in teams]
    bank = list(_TEAM_CLUSTER_COLOR_BANK)
    assert ordered == bank + [bank[0]]


def test_team_cluster_color_highlight_exempt_on_stack_cell():
    rows = [
        _row("Player A", team="NYY", ev=0.08),
        _row("Player B", team="NYY", ev=0.06),
    ]
    table = format_ev_opportunities_table(rows, highlight=lambda r: True, color_ev=True)
    for line in table.splitlines()[2:]:
        if "▌" not in line:
            continue
        stack = line.split(" | ")[_STACK_CELL_INDEX]
        assert stack.startswith("\033[38;5;")
        assert "\033[1;33m" not in stack


def test_team_cluster_marker_cross_league_no_color():
    rows = [
        _row("Twins Player", team="MIN", league="MLB", ev=0.05),
        _row("Lynx Player", team="MIN", league="WNBA", ev=0.04),
    ]
    table = format_ev_opportunities_table(rows, color_ev=True)
    for line in table.splitlines()[2:]:
        assert "▌" not in line
        assert _stack_cell_ansi_code(line) is None


def test_team_cluster_marker_plain_path_no_ansi():
    rows = [
        _row("Player A", team="NYY", ev=0.08),
        _row("Player B", team="NYY", ev=0.06),
    ]
    table = format_ev_opportunities_table(rows)
    assert "▌" in table
    for line in table.splitlines()[2:]:
        assert "\033[" not in line
