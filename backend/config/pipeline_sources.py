"""Pipeline source registry: DFS apps, sportsbooks, and supported leagues."""

from __future__ import annotations

# Betr GraphQL League enum → DraftKings slate key (dk_subcategories.DK_LEAGUE_SLATES).
BETR_TO_DK_LEAGUE: dict[str, str] = {
    "NBA": "nba",
    "MLB": "mlb",
    "WNBA": "wnba",
}

PIPELINE_LEAGUES: tuple[str, ...] = tuple(BETR_TO_DK_LEAGUE.keys())

# DFS platforms (parlay targets). User tags new DFS apps here.
DFS_SOURCES: tuple[str, ...] = ("betr",)

# Sharp / reference sportsbooks.
BOOK_SOURCES: tuple[str, ...] = ("dk", "fd", "espn")

# normalize.py PLATFORM_CONFIG keys
DFS_TO_PLATFORM: dict[str, str] = {
    "betr": "betr",
}
BOOK_TO_PLATFORM: dict[str, str] = {
    "dk": "draftkings",
    "fd": "fanduel",
    "espn": "espn",
}

SOURCE_TO_PLATFORM: dict[str, str] = {**DFS_TO_PLATFORM, **BOOK_TO_PLATFORM}


def dk_league_key(betr_league: str) -> str:
    """Map pipeline league (Betr enum) to DraftKings slate key."""
    return BETR_TO_DK_LEAGUE.get(betr_league.upper(), betr_league.lower())


def normalize_league(league: str) -> str:
    """Normalize league token to uppercase enum (NBA, MLB, WNBA)."""
    return league.upper()


def parse_csv_sources(
    value: str | None,
    *,
    valid: tuple[str, ...],
    label: str,
) -> tuple[str, ...] | None:
    """Parse comma-separated source names; None means use defaults."""
    if value is None:
        return None
    tokens = [part.strip().lower() for part in value.split(",") if part.strip()]
    if not tokens:
        raise ValueError(f"--{label} requires at least one value")
    unknown = sorted(set(tokens) - set(valid))
    if unknown:
        raise ValueError(
            f"unknown {label} source(s): {', '.join(unknown)}; "
            f"valid: {', '.join(valid)}"
        )
    return tuple(dict.fromkeys(tokens))


def parse_leagues(value: str | None) -> tuple[str, ...] | None:
    """Parse comma-separated leagues; None means all PIPELINE_LEAGUES."""
    if value is None:
        return None
    tokens = [normalize_league(part) for part in value.split(",") if part.strip()]
    if not tokens:
        raise ValueError("--leagues requires at least one value")
    unknown = sorted(set(tokens) - set(PIPELINE_LEAGUES))
    if unknown:
        raise ValueError(
            f"unknown league(s): {', '.join(unknown)}; "
            f"valid: {', '.join(PIPELINE_LEAGUES)}"
        )
    return tuple(dict.fromkeys(tokens))
