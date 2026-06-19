"""Format EV opportunity rows for pipeline / CLI output."""

from __future__ import annotations

import unicodedata

# Column order for pipeline_runner / run_ev_scan console table.
EV_TABLE_HEADERS: tuple[str, ...] = (
    "Player",
    "Lg",
    "Side",
    "Stat",
    "Line",
    "Hit%",
    "EV%",
    "DK",
    "FD",
    "Src",
    "Live",
)

# Minimum column widths (excluding separator spaces). Stat widened for longer markets.
EV_TABLE_WIDTHS: tuple[int, ...] = (16, 4, 4, 10, 4, 5, 5, 10, 10, 9, 4)

# Shorter labels for console table (raw values still in JSON output).
_LINE_SOURCE_DISPLAY: dict[str, str] = {
    "multi_book_consensus": "mb_cons",
    "dk_milestone_exact": "ms🔶",
    "ou_ms_combo": "ou+ms🔶",
}


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


def _format_line_source(value: str) -> str:
    return _LINE_SOURCE_DISPLAY.get(value, value)


def _display_width(text: str) -> int:
    """Terminal column count (wide chars such as emoji count as 2)."""
    width = 0
    for ch in text:
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


def format_ev_opportunity_row(row: dict) -> str:
    """One pipeline table row: player | lg | side | stat | line | hit% | ev | dk | fd | src | live."""
    line = row.get("line")
    line_text = str(int(line)) if line is not None and float(line) == int(float(line)) else str(line)
    hit_pct = row.get("side_hit_pct")
    hit_text = f"{hit_pct:.1f}%" if hit_pct is not None else "—"
    ev_pct = row.get("ev_pct")
    ev_text = f"{ev_pct:+.1f}" if ev_pct is not None else "—"
    live_text = "L" if row.get("is_live") else "—"

    cells = (
        row.get("player", ""),
        _format_league(row.get("league")),
        str(row.get("side", "")).upper(),
        row.get("market", ""),
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
        _format_line_source(str(row.get("line_source", ""))),
        live_text,
    )
    return " | ".join(
        _cell(str(value), width)
        for value, width in zip(cells, EV_TABLE_WIDTHS, strict=True)
    )


def format_ev_opportunities_table(rows: list[dict]) -> str:
    """Header + body lines for ranked EV opportunities."""
    lines = [format_ev_table_header(), "-" * len(format_ev_table_header())]
    lines.extend(format_ev_opportunity_row(row) for row in rows)
    return "\n".join(lines)
