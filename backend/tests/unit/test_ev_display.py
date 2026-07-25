import re

import pytest

from config.team_abbrev import TEAM_ABBR_ALIASES, TEAM_FULL_NAME_TO_ABBR
from core.ev_display import (
    _CONFIDENCE_MUTE_GREY,
    _MILESTONE_GLYPH,
    _SRC_ADJ_METHODS,
    _SRC_EXACT_METHODS,
    _TEAM_CLUSTER_COLOR_BANK,
    EV_TABLE_HEADERS,
    EV_TABLE_WIDTHS,
    MARKET_ABBREV,
    _display_width,
    _ev_tier_color_code,
    _format_game,
    _format_src,
    column_index,
    format_ev_opportunities_table,
    format_ev_opportunity_row,
    format_ev_table_header,
    format_ou_odds,
)
from core.line_adjustment import EV_ELIGIBLE_ADJUSTMENT_METHODS

# Derive Src / odds soft-price labels from the formatters under test — never restate the glyph.
_MS_SRC_LABEL = _format_src({"line_source": "milestone_exact"})
_SOFT_ODDS_SAMPLE = format_ou_odds(-165, None, milestone_one_sided=True)


def _cell_by_header(line: str, header: str) -> str:
    """Column value by header name, so tests survive a column reorder."""
    return line.split(" | ")[EV_TABLE_HEADERS.index(header)].strip()


def _stack_cell_ansi_code(line: str) -> int | None:
    cell = line.split(" | ")[column_index("stack")]
    match = re.search(r"\033\[38;5;(\d+)m", cell)
    return int(match.group(1)) if match else None


def test_format_ou_odds():
    assert format_ou_odds(110, -140) == "+110/-140"
    assert format_ou_odds(-110, -110) == "-110/-110"
    assert format_ou_odds(None, None) == "—"
    assert format_ou_odds(-165, None, milestone_one_sided=True) == f"-165/{_MILESTONE_GLYPH}"
    assert _MILESTONE_GLYPH in _SOFT_ODDS_SAMPLE
    assert "🔶" not in _SOFT_ODDS_SAMPLE


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
    """A book's one-sided milestone shows the soft glyph without claiming the Src."""
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
    assert _cell_by_header(line, "FD") == _SOFT_ODDS_SAMPLE
    assert _cell_by_header(line, "Src") == "exact"
    _assert_row_column_widths(line)


def _src_for(line_source: str, **extra) -> str:
    row = {"player": "P", "league": "MLB", "side": "over", "market": "hits",
           "line": 1.5, "line_source": line_source, **extra}
    return _cell_by_header(format_ev_opportunity_row(row), "Src")


# The complete Src vocabulary. Anything outside this is a leak of engine internals.
# Glyph derived from _format_src so a swap cannot silently leave this regex asserting the old char.
_SRC_LABEL_RE = re.compile(
    rf"^(exact(·\d+)?|{re.escape(_MS_SRC_LABEL)}|adj|\?)$"
)

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
    assert _src_for("milestone_exact") == _MS_SRC_LABEL
    assert "🔶" not in _MS_SRC_LABEL
    assert _MILESTONE_GLYPH in _MS_SRC_LABEL


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
    assert table.splitlines()[0].split(" | ")[column_index("stack")] == "▌"


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


def _row(player, *, team, league="MLB", market="hits", line=1.5, ev=0.05, ev_pct=5.0,
         line_source="exact"):
    return {
        "player": player,
        "league": league,
        "team": team,
        "side": "over",
        "market": market,
        "line": line,
        "ev": ev,
        "ev_pct": ev_pct,
        "line_source": line_source,
    }


def _row_is_dimmed(line: str) -> bool:
    """True when non-stack cells carry the dim SGR attribute (Stack is exempt by registry)."""
    cells = line.split(" | ")
    stack_i = column_index("stack")
    for index, cell in enumerate(cells):
        if index == stack_i:
            continue
        # Dim may be sole (`\033[2m`) or composed (`\033[2;…` / `\033[1;2;…`).
        if re.search(r"\033\[[0-9;]*\b2[;m]", cell):
            return True
    return False


def _stack_cell(line: str) -> str:
    return line.split(" | ")[column_index("stack")]


def _stack_has_dim(line: str) -> bool:
    return bool(re.search(r"\033\[[0-9;]*\b2[;m]", _stack_cell(line)))


def test_team_cluster_marker_marks_every_row_in_cluster():
    """Marker = team membership; dim carries per-player redundancy."""
    rows = [
        _row("Player A", team="NYY", market="hits", ev=0.08, ev_pct=8.0),
        _row("Player A", team="NYY", market="runs", line=0.5, ev=0.03, ev_pct=3.0),
        _row("Player B", team="NYY", market="hits", ev=0.06, ev_pct=6.0),
        _row("Player B", team="NYY", market="rbis", line=0.5, ev=0.04, ev_pct=4.0),
    ]
    table = format_ev_opportunities_table(rows, color_ev=True)
    body = table.splitlines()[2:]
    assert all("▌" in line for line in body)
    # Best-EV exact per player stays bright; the other dims.
    assert not _row_is_dimmed(body[0])
    assert _row_is_dimmed(body[1])
    assert not _row_is_dimmed(body[2])
    assert _row_is_dimmed(body[3])


def test_team_cluster_marker_lone_player_multiple_props_unmarked():
    """Lone player: no marker, but non-best rows still dim (dim is not cluster-gated)."""
    rows = [
        _row("Solo Star", team="NYY", market="hits", ev=0.08),
        _row("Solo Star", team="NYY", market="runs", line=0.5, ev=0.03),
    ]
    table = format_ev_opportunities_table(rows, color_ev=True)
    body = table.splitlines()[2:]
    for line in body:
        assert "▌" not in line
    assert not _row_is_dimmed(body[0])
    assert _row_is_dimmed(body[1])


def test_team_cluster_marker_cross_league_abbrev_no_false_positive():
    rows = [
        _row("Twins Player", team="MIN", league="MLB", ev=0.05),
        _row("Lynx Player", team="MIN", league="WNBA", ev=0.04),
    ]
    table = format_ev_opportunities_table(rows)
    for line in table.splitlines()[2:]:
        assert "▌" not in line


def test_team_cluster_marker_ev_tie_first_row_wins():
    """Within-tier EV ties: first row stays bright; the rest dim."""
    rows = [
        _row("Player A", team="NYY", market="hits", ev=0.05),
        _row("Player A", team="NYY", market="runs", line=0.5, ev=0.05),
        _row("Player B", team="NYY", market="hits", ev=0.04),
    ]
    table = format_ev_opportunities_table(rows, color_ev=True)
    body = table.splitlines()[2:]
    assert all("▌" in line for line in body)
    assert not _row_is_dimmed(body[0])
    assert _row_is_dimmed(body[1])
    assert not _row_is_dimmed(body[2])


def test_best_pick_is_per_trust_tier():
    """A weak exact must not dim a stronger ms — each tier keeps its own champion."""
    rows = [
        _row("Mixed", team="NYY", market="hits", ev=0.02, ev_pct=2.0, line_source="exact"),
        _row(
            "Mixed",
            team="NYY",
            market="runs",
            line=0.5,
            ev=0.10,
            ev_pct=10.0,
            line_source="milestone_exact",
        ),
        _row("Other", team="NYY", market="hits", ev=0.01, ev_pct=1.0),
    ]
    table = format_ev_opportunities_table(rows, color_ev=True)
    body = table.splitlines()[2:]
    assert not _row_is_dimmed(body[0])
    assert not _row_is_dimmed(body[1])


def test_within_tier_non_champion_dims():
    """Two exacts (or two ms): only the best-EV row in that tier stays bright."""
    rows = [
        _row("A", team="NYY", market="hits", ev=0.08, line_source="exact"),
        _row("A", team="NYY", market="runs", line=0.5, ev=0.03, line_source="exact"),
        _row("B", team="NYY", market="hits", ev=0.01, line_source="exact"),
    ]
    table = format_ev_opportunities_table(rows, color_ev=True)
    body = table.splitlines()[2:]
    assert not _row_is_dimmed(body[0])
    assert _row_is_dimmed(body[1])


def test_highlight_beats_dim():
    rows = [
        _row("Solo", team="NYY", market="hits", ev=0.08),
        _row("Solo", team="NYY", market="runs", line=0.5, ev=0.03),
    ]
    table = format_ev_opportunities_table(
        rows,
        highlight=lambda r: r.get("market") == "runs",
        color_ev=True,
    )
    body = table.splitlines()[2:]
    assert not _row_is_dimmed(body[1])
    player = body[1].split(" | ")[column_index("player")]
    assert player.startswith("\033[1;33m")
    # Must not compose bold+dim (`1;2`) — annotate clears dim before the styler.
    assert ";2" not in player.split("m", 1)[0]
    assert not re.search(r"\033\[[0-9;]*\b2[;m]", player)


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
    ev_cell = line.split(" | ")[column_index("ev")]
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
    ev_i = column_index("ev")
    assert cells[ev_i].startswith("\033[1;38;5;40m")
    assert cells[ev_i - 1].startswith("\033[1;33m")
    assert cells[ev_i + 1].startswith("\033[1;33m")


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
    marked = [line for line in table.splitlines()[2:] if "▌" in line]
    codes = [_stack_cell_ansi_code(line) for line in marked]
    assert len(codes) == len(marked) == len(rows)
    assert set(codes) == {_TEAM_CLUSTER_COLOR_BANK[0]}


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
        # Strip ANSI before parsing the player token.
        player = re.sub(r"\033\[[0-9;]*m", "", player).strip()
        team = player.split("-", 1)[1]
        code = _stack_cell_ansi_code(line)
        assert code is not None
        first_color_by_team.setdefault(team, code)
    ordered = [first_color_by_team[t] for t in teams]
    bank = list(_TEAM_CLUSTER_COLOR_BANK)
    assert ordered == bank + [bank[0]]


def test_team_cluster_color_highlight_and_dim_exempt_on_stack_cell():
    rows = [
        _row("Player A", team="NYY", market="hits", ev=0.08),
        _row("Player A", team="NYY", market="runs", line=0.5, ev=0.03),
        _row("Player B", team="NYY", ev=0.06),
    ]
    # Highlight only A's best row so the non-best row stays dimmed (dim actually fires).
    table = format_ev_opportunities_table(
        rows,
        highlight=lambda r: r.get("player") == "Player A" and r.get("market") == "hits",
        color_ev=True,
    )
    body = table.splitlines()[2:]
    assert _row_is_dimmed(body[1])
    for line in body:
        stack = _stack_cell(line)
        assert stack.startswith("\033[38;5;")
        assert "\033[1;33m" not in stack
        assert not _stack_has_dim(line)


def test_blank_stack_cell_exempt_from_dim():
    """Lone-player dim: blank Stack has no marker colour, so exempt_dim is load-bearing."""
    rows = [
        _row("Solo Star", team="NYY", market="hits", ev=0.08),
        _row("Solo Star", team="NYY", market="runs", line=0.5, ev=0.03),
    ]
    table = format_ev_opportunities_table(rows, color_ev=True)
    dim_line = table.splitlines()[3]
    assert _row_is_dimmed(dim_line)
    assert "▌" not in dim_line
    assert not _stack_has_dim(dim_line)
    assert "\033[" not in _stack_cell(dim_line)


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


def test_dim_composes_with_ev_tier_in_one_escape():
    rows = [
        _row("Solo", team="NYY", market="hits", ev=0.08, ev_pct=8.0),
        _row("Solo", team="NYY", market="runs", line=0.5, ev=0.03, ev_pct=3.0),
    ]
    table = format_ev_opportunities_table(rows, color_ev=True)
    ev_cell = table.splitlines()[3].split(" | ")[column_index("ev")]
    assert ev_cell.startswith("\033[2;38;5;40m")
    assert "\033[2m\033[38;5;" not in ev_cell


def _strip_cell_ansi(cell: str) -> str:
    return re.sub(r"\033\[[0-9;]*m", "", cell)


def _cell_has_grey(cell: str) -> bool:
    return f"38;5;{_CONFIDENCE_MUTE_GREY}m" in cell


def _cell_has_ev_tier(cell: str) -> bool:
    """True when an EV-tier xterm code (not mute grey) is present."""
    return bool(re.search(r"38;5;(?!245)(\d+)m", cell))


def test_confidence_mute_greys_credibility_cells_on_ms_only():
    ms = _row(
        "Ms Player",
        team="NYY",
        market="hits",
        ev=0.05,
        ev_pct=5.0,
        line_source="milestone_exact",
    )
    ms["side_hit_pct"] = 55.0
    exact = _row(
        "Exact Player",
        team="NYY",
        market="hits",
        ev=0.04,
        ev_pct=4.0,
        line_source="exact",
    )
    exact["side_hit_pct"] = 52.0
    table = format_ev_opportunities_table([ms, exact], color_ev=True)
    ms_line, exact_line = table.splitlines()[2], table.splitlines()[3]
    for header in ("Hit%", "EV%", "Src"):
        ms_cell = ms_line.split(" | ")[EV_TABLE_HEADERS.index(header)]
        exact_cell = exact_line.split(" | ")[EV_TABLE_HEADERS.index(header)]
        assert _cell_has_grey(ms_cell), header
        assert not _cell_has_grey(exact_cell), header
    assert not _cell_has_ev_tier(ms_line.split(" | ")[column_index("ev")])
    assert _cell_has_ev_tier(exact_line.split(" | ")[column_index("ev")])
    # Identity cells stay bright (no mute grey).
    assert not _cell_has_grey(ms_line.split(" | ")[column_index("player")])
    assert not _cell_has_grey(ms_line.split(" | ")[column_index("stat")])
    assert _strip_cell_ansi(ms_line.split(" | ")[column_index("src")]).strip() == _MS_SRC_LABEL


def test_confidence_mute_independent_of_dim():
    """Dim and mute are separate channels — both detectable on a non-best ms row."""
    rows = [
        _row("P", team="NYY", market="hits", ev=0.10, ev_pct=10.0, line_source="milestone_exact"),
        _row(
            "P",
            team="NYY",
            market="runs",
            line=0.5,
            ev=0.02,
            ev_pct=2.0,
            line_source="milestone_exact",
        ),
        _row("Q", team="NYY", market="hits", ev=0.01, ev_pct=1.0),
    ]
    for row in rows:
        row["side_hit_pct"] = 50.0
    table = format_ev_opportunities_table(rows, color_ev=True)
    dim_ms = table.splitlines()[3]
    assert _row_is_dimmed(dim_ms)
    ev_cell = dim_ms.split(" | ")[column_index("ev")]
    assert ev_cell.startswith(f"\033[2;38;5;{_CONFIDENCE_MUTE_GREY}m")
    assert f"38;5;{_CONFIDENCE_MUTE_GREY}m" in dim_ms.split(" | ")[column_index("hit")]
    assert f"38;5;{_CONFIDENCE_MUTE_GREY}m" in dim_ms.split(" | ")[column_index("src")]


def test_highlighted_ms_gets_bold_grey_never_bold_tier():
    row = _row("P", team="NYY", market="hits", ev=0.05, ev_pct=5.0, line_source="milestone_exact")
    row["side_hit_pct"] = 55.0
    table = format_ev_opportunities_table([row], highlight=lambda r: True, color_ev=True)
    ev_cell = table.splitlines()[2].split(" | ")[column_index("ev")]
    assert ev_cell.startswith(f"\033[1;38;5;{_CONFIDENCE_MUTE_GREY}m")
    assert not _cell_has_ev_tier(ev_cell)


def test_glyph_substring_grey_on_exact_row_soft_book():
    """Case 10: soft ◆ on an otherwise-bright exact row greys only the glyph, not Hit%/EV%/Src."""
    row = {
        "player": "Junior Perez",
        "league": "MLB",
        "team": "CIN",
        "side": "over",
        "market": "h+r+rbi",
        "line": 0.5,
        "side_hit_pct": 52.0,
        "ev": 0.05,
        "ev_pct": 5.0,
        "fd_over_odds": -165,
        "fd_under_odds": None,
        "fd_milestone_one_sided": True,
        "line_source": "fd_exact",
    }
    table = format_ev_opportunities_table([row], color_ev=True)
    line = table.splitlines()[2]
    fd_cell = line.split(" | ")[column_index("fd")]
    assert _MILESTONE_GLYPH in _strip_cell_ansi(fd_cell)
    assert f"\033[38;5;{_CONFIDENCE_MUTE_GREY}m{_MILESTONE_GLYPH}" in fd_cell
    # Odds value beside the glyph is not wrapped in mute grey as a whole-cell style.
    assert not fd_cell.startswith(f"\033[38;5;{_CONFIDENCE_MUTE_GREY}m")
    for header in ("Hit%", "EV%", "Src"):
        cell = line.split(" | ")[EV_TABLE_HEADERS.index(header)]
        assert not _cell_has_grey(cell), header
    assert _cell_has_ev_tier(line.split(" | ")[column_index("ev")])


@pytest.mark.parametrize(
    "dim,highlight,cluster,ms",
    [
        pytest.param(False, False, False, False, id="plain-exact"),
        pytest.param(True, False, False, False, id="dim-exact"),
        pytest.param(False, True, False, False, id="hl-exact"),
        pytest.param(True, True, False, False, id="dim-hl-exact-hl-wins"),
        pytest.param(False, False, True, False, id="cluster-exact"),
        pytest.param(False, False, False, True, id="mute-ms"),
        pytest.param(True, False, False, True, id="dim-mute-ms"),
        pytest.param(False, True, False, True, id="hl-mute-ms"),
        pytest.param(True, False, True, True, id="dim-cluster-mute-ms"),
    ],
)
def test_style_layer_matrix(dim, highlight, cluster, ms):
    """Layer interactions named by combination; failure names the offender."""
    line_source = "milestone_exact" if ms else "exact"
    if cluster:
        rows = [
            _row("A", team="NYY", market="hits", ev=0.10, ev_pct=10.0, line_source=line_source),
            _row(
                "A",
                team="NYY",
                market="runs",
                line=0.5,
                ev=0.02,
                ev_pct=2.0,
                line_source=line_source,
            ),
            _row("B", team="NYY", market="hits", ev=0.01, ev_pct=1.0),
        ]
        target = 1 if dim else 0
    else:
        rows = [
            _row("Solo", team="NYY", market="hits", ev=0.10, ev_pct=10.0, line_source=line_source),
            _row(
                "Solo",
                team="NYY",
                market="runs",
                line=0.5,
                ev=0.02,
                ev_pct=2.0,
                line_source=line_source,
            ),
        ]
        target = 1 if dim else 0
    for row in rows:
        row["side_hit_pct"] = 50.0

    def _hl(r: dict) -> bool:
        return highlight and r is rows[target]

    table = format_ev_opportunities_table(rows, highlight=_hl, color_ev=True)
    line = table.splitlines()[2 + target]
    expect_dim = dim and not highlight
    assert _row_is_dimmed(line) is expect_dim
    if cluster:
        assert "▌" in line
        assert _stack_cell_ansi_code(line) is not None
        assert not _stack_has_dim(line)
    ev_cell = line.split(" | ")[column_index("ev")]
    if ms:
        assert _cell_has_grey(ev_cell)
        assert not _cell_has_ev_tier(ev_cell)
        if highlight:
            assert ev_cell.startswith(f"\033[1;38;5;{_CONFIDENCE_MUTE_GREY}m")
        elif expect_dim:
            assert ev_cell.startswith(f"\033[2;38;5;{_CONFIDENCE_MUTE_GREY}m")
    else:
        assert not _cell_has_grey(ev_cell)
        assert _cell_has_ev_tier(ev_cell)