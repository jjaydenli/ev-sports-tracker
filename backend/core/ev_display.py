"""Format EV opportunity rows for pipeline / CLI output."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass

# Column order for pipeline_runner / run_ev_scan console table.
# The stack column is a colour swatch, not a word. Its header is an uncoloured marker: it keeps
# the column at marker width and previews the glyph in the neutral "no cluster" colour, so the
# column self-describes without a header word. Deliberately plain — format_ev_table_header() must
# stay ANSI-free for non-terminal consumers.
_STACK_HEADER = "▌"

# Soft-price milestone glyph in odds / Src cells. Character only — ANSI is applied by the
# per-cell composer (substring grey), never by value-formatters. Commit 3 swaps 🔶 → ◆.
_MILESTONE_GLYPH = "🔶"
_CONFIDENCE_MUTE_GREY = 245

_TEAM_CLUSTER_MARKER = "▌"
_TEAM_CLUSTER_COLOR_BANK: tuple[int, ...] = (33, 208, 51, 201, 99, 30)

_RESET = "\033[0m"

_ANSI_ESCAPE = re.compile(r"\033\[[0-9;]*m")

# Src taxonomy: two roots (a real quote, or an inferred one) — never a raw method string.
# Book identity and main-vs-alt are trust-neutral and stay in board.json's sharp_by_book.
_SRC_EXACT_METHODS: frozenset[str] = frozenset(
    {"exact", "dk_alt", "fd_exact", "fd_alt", "espn_exact", "espn_alt"}
)
# Adjusted lines keep their full adjustment_method in JSON; the terminal shows one quiet
# umbrella, never the verbose interp string. Only dk_interpolated can actually reach
# the board (is_ev_eligible_quote, line_adjustment.py:78); milestone_interpolated is defensive
# (display-only, never EV-eligible).
_SRC_ADJ_METHODS: frozenset[str] = frozenset(
    {
        "dk_interpolated",
        "milestone_interpolated",
    }
)
_SRC_UNKNOWN = "?"

# Betting-idiomatic market abbreviations, keyed on canonical markets (config/market_maps.py).
# Extend alongside any new canonical market; unmapped markets fall through to the raw name.
# Bare single letters and team-code collisions are spelled out; established multi-letter
# notation is kept as-is.
MARKET_ABBREV: dict[str, str] = {
    # MLB — batting
    "hits": "HITS",
    # "TB" is standard notation but collides with the Tampa Bay Rays team code, which
    # renders a few columns away in Game (e.g. "[TB]@NYY | ▲ | TB").
    "total_bases": "BASES",
    "home_runs": "HR",
    "h+r+rbi": "H+R+RBI",
    "rbi": "RBI",
    "runs": "RUNS",
    "singles": "1B",
    "doubles": "2B",
    "walks": "BB",
    # MLB — pitching ("_A" = allowed, to stay distinct from the batting markets; box scores
    # reuse H/BB for both because batting and pitching live in separate tables — ours do not).
    "strikeouts": "K",
    "earned_runs": "ER",
    "total_outs": "OUTS",
    "hits_allowed": "HITS_A",
    "pitching_walks": "BB_A",
    # NBA / WNBA — official NBA/WNBA glossary notation
    "points": "PTS",
    "rebounds": "REB",
    "assists": "AST",
    "threes": "3PM",
    "steals": "STL",
    "blocks": "BLK",
    "turnovers": "TOV",
    "fouls": "PF",
    "fg_made": "FGM",
    "fg_attempted": "FGA",
    "ft_made": "FTM",
    "ft_attempted": "FTA",
    "3pt_att": "3PA",
    "fantasy_pts": "FPTS",
    "stl+blk": "STL+BLK",
    "pra": "PRA",
    "pts+reb": "PTS+REB",
    "pts+ast": "PTS+AST",
    "reb+ast": "REB+AST",
}

_SIDE_GLYPH: dict[str, str] = {"over": "▲", "under": "▼"}


@dataclass(frozen=True)
class _Column:
    """One EV table column. Style roles are declarative so the composer can compose SGR codes.

    Commit-3 fit (sketched before commit 1 lands):
    - credibility=True → colour-substitute Hit%/Src (and EV%) with mute grey on ms rows.
    - ev_tier=True + credibility=True on EV% → grey wins over tier ramp (mutually exclusive).
    - soft_glyph=True on odds cols → substring-level grey on the milestone glyph only.
    Stack exemptions live here, not as ``if index ==`` branches in the styler.
    """

    key: str
    header: str
    width: int
    exempt_highlight: bool = False
    exempt_dim: bool = False
    cluster_swatch: bool = False
    ev_tier: bool = False
    credibility: bool = False
    soft_glyph: bool = False


# Ordered column registry — single source for headers, widths, render order, and style roles.
_COLUMNS: tuple[_Column, ...] = (
    _Column("player", "Player", 16),
    _Column("league", "Lg", 4),
    _Column(
        "stack",
        _STACK_HEADER,
        1,
        exempt_dim=True,
        cluster_swatch=True,
    ),
    _Column("game", "Game", 9),
    _Column("side", "Side", 4),
    _Column("stat", "Stat", 7),
    _Column("line", "Line", 4),
    _Column("hit", "Hit%", 5, credibility=True),
    _Column("ev", "EV%", 5, ev_tier=True, credibility=True),
    _Column("dk", "DK", 10, soft_glyph=True),
    _Column("fd", "FD", 10, soft_glyph=True),
    _Column("espn", "ESPN", 10, soft_glyph=True),
    _Column("src", "Src", 7, credibility=True),
    _Column("live", "Live", 4),
)

EV_TABLE_HEADERS: tuple[str, ...] = tuple(col.header for col in _COLUMNS)
EV_TABLE_WIDTHS: tuple[int, ...] = tuple(col.width for col in _COLUMNS)

_COLUMN_BY_KEY: dict[str, int] = {col.key: index for index, col in enumerate(_COLUMNS)}


def column_index(key: str) -> int:
    """Registry accessor for tests and callers that address a column by key."""
    try:
        return _COLUMN_BY_KEY[key]
    except KeyError as exc:
        raise KeyError(f"unknown EV table column {key!r}") from exc


# Derived from the registry (not hand-maintained literals).
_EV_CELL_INDEX = column_index("ev")
_STACK_CELL_INDEX = column_index("stack")


@dataclass(frozen=True)
class RowStyle:
    """Per-row display annotations produced by one annotate pass."""

    highlight: bool = False
    dimmed: bool = False
    cluster_marker: str = ""
    cluster_color: int | None = None
    ev_tier_code: int | None = None
    confidence_mute: bool = False


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
    """Format paired O/U American odds (+110/-140); milestone one-sided uses the soft glyph."""
    if over is None and under is None:
        return "—"
    under_text = (
        _MILESTONE_GLYPH
        if milestone_one_sided and under is None
        else format_american_odds(under)
    )
    return f"{format_american_odds(over)}/{under_text}"


def _format_src(row: dict) -> str:
    """Src label for a row: a real quote (exact / exact·N), or an inferred one (ms… / adj)."""
    method = str(row.get("line_source", ""))
    if method == "multi_book_consensus":
        books = row.get("sharp_books") or ()
        return f"exact·{len(books)}" if len(books) > 1 else "exact"
    if method in _SRC_EXACT_METHODS:
        return "exact"
    if method == "milestone_exact":
        return f"ms{_MILESTONE_GLYPH}"
    if method in _SRC_ADJ_METHODS:
        return "adj"
    return _SRC_UNKNOWN


def _format_market(value: str | None) -> str:
    """Betting-idiomatic abbreviation; unmapped markets fall through to the raw name."""
    market = str(value or "")
    return MARKET_ABBREV.get(market, market)


def _format_side(value: str | None) -> str:
    """▲/▼ for over/under; any other side (e.g. an O/U collapse) renders as its own label."""
    side = str(value or "").strip().lower()
    return _SIDE_GLYPH.get(side, str(value or "").upper())


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
    """Raw cell text before padding (one per registry column)."""
    line = row.get("line")
    line_text = str(int(line)) if line is not None and float(line) == int(float(line)) else str(line)
    hit_pct = row.get("side_hit_pct")
    hit_text = f"{hit_pct:.1f}%" if hit_pct is not None else "—"
    ev_pct = row.get("ev_pct")
    ev_text = f"{ev_pct:+.1f}" if ev_pct is not None else "—"
    live_text = "L" if row.get("is_live") else "—"

    by_key = {
        "player": str(row.get("player", "")),
        "league": _format_league(row.get("league")),
        "stack": marker,
        "game": _format_game(row.get("game"), row.get("team")),
        "side": _format_side(row.get("side")),
        "stat": _format_market(row.get("market")),
        "line": line_text,
        "hit": hit_text,
        "ev": ev_text,
        "dk": format_ou_odds(
            row.get("dk_over_odds"),
            row.get("dk_under_odds"),
            milestone_one_sided=bool(row.get("dk_milestone_one_sided")),
        ),
        "fd": format_ou_odds(
            row.get("fd_over_odds"),
            row.get("fd_under_odds"),
            milestone_one_sided=bool(row.get("fd_milestone_one_sided")),
        ),
        "espn": format_ou_odds(
            row.get("espn_over_odds"),
            row.get("espn_under_odds"),
            milestone_one_sided=bool(row.get("espn_milestone_one_sided")),
        ),
        "src": _format_src(row),
        "live": live_text,
    }
    return tuple(by_key[col.key] for col in _COLUMNS)


def _compute_team_cluster_markers(rows: list[dict]) -> list[str]:
    """Mark every row in a (league, team) group with ≥2 distinct players."""
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
        for i in indices:
            markers[i] = _TEAM_CLUSTER_MARKER
    return markers


def _best_index_by_ev(rows: list[dict], indices: list[int]) -> int:
    """Highest-ev index; ties break first-row-wins."""
    best_index = indices[0]
    best_ev = rows[best_index].get("ev")
    for i in indices[1:]:
        ev = rows[i].get("ev")
        if ev is not None and (best_ev is None or ev > best_ev):
            best_index = i
            best_ev = ev
    return best_index


def _compute_dimmed_flags(rows: list[dict]) -> list[bool]:
    """Dim each player's non-best rows per trust tier over the whole table.

    Grouping key is ``player`` alone (not re-scoped to league/team). Up to two rows
    stay bright per player: best-EV exact (if any) and best-EV ms (if any).
    ``is_exact = line_source != "milestone_exact"`` — adj shares the exact bucket.
    """
    dimmed = [False] * len(rows)
    by_player: dict[object, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        by_player[row.get("player")].append(index)

    for indices in by_player.values():
        if len(indices) < 2:
            continue
        exact_indices = [
            i for i in indices if rows[i].get("line_source") != "milestone_exact"
        ]
        ms_indices = [
            i for i in indices if rows[i].get("line_source") == "milestone_exact"
        ]
        champions: set[int] = set()
        if exact_indices:
            champions.add(_best_index_by_ev(rows, exact_indices))
        if ms_indices:
            champions.add(_best_index_by_ev(rows, ms_indices))
        for i in indices:
            if i not in champions:
                dimmed[i] = True
    return dimmed


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


def _sgr(codes: list[str]) -> str:
    return f"\033[{';'.join(codes)}m" if codes else ""


def _apply_cell_styles(
    padded_cells: list[str],
    style: RowStyle,
    *,
    color_ev: bool,
) -> list[str]:
    """Compose per-cell SGR codes from RowStyle + column registry roles (not if/elif select)."""
    if not style.highlight and not color_ev and not style.dimmed:
        return padded_cells

    styled: list[str] = []
    for col, cell in zip(_COLUMNS, padded_cells, strict=True):
        # Layer 0 — cluster swatch: full colour, never highlight/dim.
        if col.cluster_swatch and style.cluster_color is not None and color_ev:
            styled.append(f"\033[38;5;{style.cluster_color}m{cell}{_RESET}")
            continue

        codes: list[str] = []
        if style.highlight and not col.exempt_highlight:
            codes.append("1")
        elif style.dimmed and not col.exempt_dim:
            codes.append("2")

        # Foreground: confidence-mute grey and EV tier are mutually exclusive (grey wins).
        if color_ev and style.confidence_mute and col.credibility:
            codes.append(f"38;5;{_CONFIDENCE_MUTE_GREY}")
        elif color_ev and col.ev_tier and style.ev_tier_code is not None:
            codes.append(f"38;5;{style.ev_tier_code}")
        elif style.highlight and not col.exempt_highlight:
            codes.append("33")

        # soft_glyph substring grey is intentionally not applied yet — commit 3 activates
        # it alongside the 🔶→◆ swap. Registry flag is already on DK/FD/ESPN so that commit
        # only flips the composer path, not the column descriptors.
        if codes:
            styled.append(f"{_sgr(codes)}{cell}{_RESET}")
        else:
            styled.append(cell)
    return styled


def _annotate_row(
    row: dict,
    *,
    highlight: bool,
    color_ev: bool,
    cluster_marker: str = "",
    cluster_color: int | None = None,
    dimmed: bool = False,
    confidence_mute: bool = False,
) -> RowStyle:
    """Build RowStyle for one row. Highlight beats dim (resolved here, not in the styler)."""
    if highlight:
        dimmed = False
    ev_pct = row.get("ev_pct")
    ev_tier_code = (
        _ev_tier_color_code(ev_pct) if color_ev and ev_pct is not None else None
    )
    return RowStyle(
        highlight=highlight,
        dimmed=dimmed,
        cluster_marker=cluster_marker,
        cluster_color=cluster_color,
        ev_tier_code=ev_tier_code,
        confidence_mute=confidence_mute,
    )


def _format_ev_row_cells(
    row: dict,
    style: RowStyle,
    *,
    color_ev: bool = False,
) -> list[str]:
    values = _ev_row_cell_values(row, marker=style.cluster_marker)
    padded = [
        _cell(value, width)
        for value, width in zip(values, EV_TABLE_WIDTHS, strict=True)
    ]
    return _apply_cell_styles(padded, style, color_ev=color_ev)


def format_ev_opportunity_row(row: dict, *, color_ev: bool = False) -> str:
    """One pipeline table row with optional EV coloring (no cluster — table path owns that)."""
    style = _annotate_row(row, highlight=False, color_ev=color_ev)
    return " | ".join(_format_ev_row_cells(row, style, color_ev=color_ev))


def format_ev_opportunities_table(
    rows: list[dict],
    *,
    highlight: Callable[[dict], bool] | None = None,
    color_ev: bool = False,
) -> str:
    """Header + body lines for ranked EV opportunities."""
    cluster_markers = _compute_team_cluster_markers(rows)
    cluster_colors = _compute_team_cluster_colors(rows, cluster_markers)
    # Dim is ANSI; gate on color_ev like cluster colour so the plain path stays escape-free.
    dim_flags = _compute_dimmed_flags(rows) if color_ev else [False] * len(rows)
    header = format_ev_table_header()
    lines = [header, "-" * _display_width(header)]
    for index, row in enumerate(rows):
        is_highlighted = highlight(row) if highlight is not None else False
        style = _annotate_row(
            row,
            highlight=is_highlighted,
            color_ev=color_ev,
            cluster_marker=cluster_markers[index],
            cluster_color=cluster_colors[index],
            dimmed=dim_flags[index],
        )
        lines.append(" | ".join(_format_ev_row_cells(row, style, color_ev=color_ev)))
    return "\n".join(lines)
