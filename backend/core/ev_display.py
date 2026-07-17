"""Format EV opportunity rows for pipeline / CLI output."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Callable

# Column order for pipeline_runner / run_ev_scan console table.
EV_TABLE_HEADERS: tuple[str, ...] = (
    "Player",
    "Lg",
    "Game",
    "Side",
    "Stat",
    "Line",
    "Hit%",
    "EV%",
    "DK",
    "FD",
    "ESPN",
    "Src",
    "Live",
    "Stack",
)

# Minimum column widths (excluding separator spaces). Stat widened for longer markets.
# Src fits the longest label ("exact·N").
EV_TABLE_WIDTHS: tuple[int, ...] = (16, 4, 9, 4, 10, 4, 5, 5, 10, 10, 10, 7, 4, 5)

_TEAM_CLUSTER_MARKER = "▌"
_TEAM_CLUSTER_COLOR_BANK: tuple[int, ...] = (33, 208, 51, 201, 99, 30)

_EV_CELL_INDEX = 7
_STACK_CELL_INDEX = 13
_HIGHLIGHT_START = "\033[1;33m"
_RESET = "\033[0m"

_ANSI_ESCAPE = re.compile(r"\033\[[0-9;]*m")

# Src taxonomy: two roots (a real quote, or an inferred one) — never a raw method string.
# Book identity and main-vs-alt are trust-neutral and stay in board.json's sharp_by_book.
_SRC_EXACT_METHODS: frozenset[str] = frozenset(
    {"exact", "dk_alt", "fd_exact", "fd_alt", "espn_exact", "espn_alt"}
)
# Adjusted lines keep their full adjustment_method in JSON; the terminal shows one quiet
# umbrella, never the verbose interp/extrap strings. Only dk_interpolated can actually reach
# the board (is_ev_eligible_quote, line_adjustment.py:78); the rest are defensive.
_SRC_ADJ_METHODS: frozenset[str] = frozenset(
    {
        "dk_interpolated",
        "dk_extrapolated",
        "dk_milestone_interpolated",
        "dk_milestone_extrapolated",
    }
)
_SRC_UNKNOWN = "?"


def format_american_odds(value: int | None) -> str:
    """Format American odds with explicit sign (+110, -140)."""
    if value is None:
        return "—"
    return f"+{value}" if value > 0 else str(value)


def format_ou_odds(
    over: int | None,
    under: int | None,
    *,
    milestone_one_sided: bool = False,
) -> str:
    """Format paired O/U American odds (+110/-140); milestone one-sided uses 🔶."""
    if over is None and under is None:
        return "—"
    under_text = "🔶" if milestone_one_sided and under is None else format_american_odds(under)
    return f"{format_american_odds(over)}/{under_text}"


def _format_src(row: dict) -> str:
    """Src label for a row: a real quote (exact / exact·N), or an inferred one (ms🔶 / adj)."""
    method = str(row.get("line_source", ""))
    if method == "multi_book_consensus":
        books = row.get("sharp_books") or ()
        return f"exact·{len(books)}" if len(books) > 1 else "exact"
    if method in _SRC_EXACT_METHODS:
        return "exact"
    if method == "dk_milestone_exact":
        return "ms🔶"
    if method in _SRC_ADJ_METHODS:
        return "adj"
    return _SRC_UNKNOWN


def _strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE.sub("", text)


def _display_width(text: str) -> int:
    """Terminal column count (wide chars such as emoji count as 2)."""
    width = 0
    for ch in _strip_ansi(text):
        if unicodedata.east_asian_width(ch) in ("F", "W"):
            width += 2
        else:
            width += 1
    return width


def _cell(text: str, width: int) -> str:
    if _display_width(text) > width:
        trimmed = ""
        budget = width - 1
        for ch in text:
            ch_width = 2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1
            if _display_width(trimmed) + ch_width > budget:
                break
            trimmed += ch
        return trimmed + "…"
    return text + (" " * (width - _display_width(text)))


def format_ev_table_header() -> str:
    return " | ".join(
        _cell(header, width)
        for header, width in zip(EV_TABLE_HEADERS, EV_TABLE_WIDTHS, strict=True)
    )


def _format_league(value: str | None) -> str:
    if not value:
        return "—"
    return str(value).upper()


def _format_game(game: str | None, team: str | None) -> str:
    """Matchup (AWAY@HOME) with the player's team in brackets."""
    if not game:
        return "—"
    game_text = str(game).strip()
    if not team or "@" not in game_text:
        return game_text
    away, home = game_text.split("@", 1)
    team_key = str(team).strip().upper()
    away_key = away.strip().upper()
    home_key = home.strip().upper()
    if team_key == away_key:
        return f"[{away}]@{home}"
    if team_key == home_key:
        return f"{away}@[{home}]"
    return game_text


def _ev_row_cell_values(row: dict, *, marker: str = "") -> tuple[str, ...]:
    """Raw cell text before padding (one per EV_TABLE_HEADERS column)."""
    line = row.get("line")
    line_text = str(int(line)) if line is not None and float(line) == int(float(line)) else str(line)
    hit_pct = row.get("side_hit_pct")
    hit_text = f"{hit_pct:.1f}%" if hit_pct is not None else "—"
    ev_pct = row.get("ev_pct")
    ev_text = f"{ev_pct:+.1f}" if ev_pct is not None else "—"
    live_text = "L" if row.get("is_live") else "—"

    return (
        str(row.get("player", "")),
        _format_league(row.get("league")),
        _format_game(row.get("game"), row.get("team")),
        str(row.get("side", "")).upper(),
        str(row.get("market", "")),
        line_text,
        hit_text,
        ev_text,
        format_ou_odds(
            row.get("dk_over_odds"),
            row.get("dk_under_odds"),
            milestone_one_sided=bool(row.get("dk_milestone_one_sided")),
        ),
        format_ou_odds(
            row.get("fd_over_odds"),
            row.get("fd_under_odds"),
            milestone_one_sided=bool(row.get("fd_milestone_one_sided")),
        ),
        format_ou_odds(
            row.get("espn_over_odds"),
            row.get("espn_under_odds"),
            milestone_one_sided=bool(row.get("espn_milestone_one_sided")),
        ),
        _format_src(row),
        live_text,
        marker,
    )


def _compute_team_cluster_markers(rows: list[dict]) -> list[str]:
    """Mark each player's best-ev row when ≥2 distinct players share (league, team)."""
    markers = [""] * len(rows)
    groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        team = row.get("team")
        if not team:
            continue
        league = row.get("league") or ""
        groups[(str(league), str(team))].append(index)

    for indices in groups.values():
        players = {rows[i].get("player") for i in indices}
        if len(players) < 2:
            continue
        for player in players:
            player_indices = [i for i in indices if rows[i].get("player") == player]
            best_index = player_indices[0]
            best_ev = rows[best_index].get("ev")
            for i in player_indices[1:]:
                ev = rows[i].get("ev")
                if ev is not None and (best_ev is None or ev > best_ev):
                    best_index = i
                    best_ev = ev
            markers[best_index] = _TEAM_CLUSTER_MARKER
    return markers


def _compute_team_cluster_colors(
    rows: list[dict],
    markers: list[str],
) -> list[int | None]:
    """xterm color per marked stack row; bank assigned on first cluster appearance, cycling."""
    colors: list[int | None] = [None] * len(rows)
    clustered_keys = {
        (str(rows[i].get("league") or ""), str(rows[i].get("team") or ""))
        for i, marker in enumerate(markers)
        if marker == _TEAM_CLUSTER_MARKER
    }
    cluster_color: dict[tuple[str, str], int] = {}
    bank_index = 0
    bank = _TEAM_CLUSTER_COLOR_BANK

    for index, row in enumerate(rows):
        key = (str(row.get("league") or ""), str(row.get("team") or ""))
        if key not in clustered_keys:
            continue
        if key not in cluster_color:
            cluster_color[key] = bank[bank_index % len(bank)]
            bank_index += 1
        if markers[index] == _TEAM_CLUSTER_MARKER:
            colors[index] = cluster_color[key]
    return colors


def _ev_tier_color_code(ev_pct: float) -> int:
    """xterm-256 color code for an EV% profitability tier."""
    if ev_pct >= 5.0:
        return 46
    if ev_pct >= 3.0:
        return 40
    if ev_pct >= 1.5:
        return 34
    if ev_pct >= 0.0:
        return 28
    if ev_pct >= -1.0:
        return 217
    if ev_pct >= -2.0:
        return 210
    return 196


def _apply_cell_styles(
    padded_cells: list[str],
    *,
    highlight: bool,
    color_ev: bool,
    ev_pct: float | None,
    cluster_color: int | None = None,
) -> list[str]:
    """Per-cell ANSI styling; combined bold+tier escape on EV% when both apply."""
    if not highlight and not color_ev:
        return padded_cells

    styled: list[str] = []
    for index, cell in enumerate(padded_cells):
        is_ev_cell = index == _EV_CELL_INDEX
        is_stack_cell = index == _STACK_CELL_INDEX

        if is_stack_cell and cluster_color is not None and color_ev:
            styled.append(f"\033[38;5;{cluster_color}m{cell}{_RESET}")
            continue

        if is_ev_cell and highlight and color_ev and ev_pct is not None:
            tier_code = _ev_tier_color_code(ev_pct)
            styled.append(f"\033[1;38;5;{tier_code}m{cell}{_RESET}")
        elif is_ev_cell and color_ev and ev_pct is not None:
            tier_code = _ev_tier_color_code(ev_pct)
            styled.append(f"\033[38;5;{tier_code}m{cell}{_RESET}")
        elif highlight:
            styled.append(f"{_HIGHLIGHT_START}{cell}{_RESET}")
        else:
            styled.append(cell)
    return styled


def _format_ev_row_cells(
    row: dict,
    *,
    highlight: bool = False,
    color_ev: bool = False,
    marker: str = "",
    cluster_color: int | None = None,
) -> list[str]:
    values = _ev_row_cell_values(row, marker=marker)
    padded = [
        _cell(value, width)
        for value, width in zip(values, EV_TABLE_WIDTHS, strict=True)
    ]
    return _apply_cell_styles(
        padded,
        highlight=highlight,
        color_ev=color_ev,
        ev_pct=row.get("ev_pct"),
        cluster_color=cluster_color,
    )


def format_ev_opportunity_row(row: dict, *, marker: str = "", color_ev: bool = False) -> str:
    """One pipeline table row with optional same-team cluster marker and EV coloring."""
    return " | ".join(_format_ev_row_cells(row, marker=marker, color_ev=color_ev))


def format_ev_opportunities_table(
    rows: list[dict],
    *,
    highlight: Callable[[dict], bool] | None = None,
    color_ev: bool = False,
) -> str:
    """Header + body lines for ranked EV opportunities."""
    cluster_markers = _compute_team_cluster_markers(rows)
    cluster_colors = _compute_team_cluster_colors(rows, cluster_markers)
    lines = [format_ev_table_header(), "-" * len(format_ev_table_header())]
    for index, row in enumerate(rows):
        is_highlighted = highlight(row) if highlight is not None else False
        lines.append(
            " | ".join(
                _format_ev_row_cells(
                    row,
                    highlight=is_highlighted,
                    color_ev=color_ev,
                    marker=cluster_markers[index],
                    cluster_color=cluster_colors[index],
                )
            )
        )
    return "\n".join(lines)
