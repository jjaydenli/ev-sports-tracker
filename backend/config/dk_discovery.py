"""DraftKings prop subCategoryId discovery helpers (ad-hoc debug only).

Used by ``scripts/probe_dk_discover.py`` — not part of the default
add-league-markets workflow. User supplies IDs via DevTools; agent verifies one at a time.
"""

from __future__ import annotations

from pathlib import Path

# Default ID ranges per DK slate key (extend when probes miss tabs).
# Override at runtime: ``python -m scripts.probe_dk_discover --ranges 6580-6760``
DK_DISCOVERY_ID_RANGES: dict[str, tuple[tuple[int, int], ...]] = {
    "nba": (
        (10400, 10800),
        (12480, 12500),
        (2699000, 2701000),
        (2716400, 2716600),
    ),
    "mlb": (
        (6580, 6760),
        (6400, 7000),
        (10400, 10800),
        (2699000, 2701000),
    ),
}

DISCOVERY_DIR = Path("data/processed/discovery")


def discovery_output_path(league: str, *, backend_root: Path | None = None) -> Path:
    """Default JSON catalog path for a league-wide prop subcategory scan."""
    base = backend_root or Path(__file__).resolve().parent.parent
    return base / DISCOVERY_DIR / f"dk_{league.lower()}_prop_subcategories.json"


def parse_id_ranges(specs: list[str]) -> tuple[tuple[int, int], ...]:
    """Parse ``START-END`` range strings (inclusive)."""
    ranges: list[tuple[int, int]] = []
    for spec in specs:
        if "-" not in spec:
            raise ValueError(f"expected START-END, got {spec!r}")
        start_s, end_s = spec.split("-", 1)
        start, end = int(start_s), int(end_s)
        if start > end:
            raise ValueError(f"invalid range {spec!r}: start > end")
        ranges.append((start, end))
    return tuple(ranges)
