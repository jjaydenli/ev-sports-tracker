"""Central cross-book team-abbreviation canonicalization.

Each book emits team codes in a slightly different vocabulary; betr (the DFS
anchor) defines the canonical form used in the display ``game`` string. The
cross-book match gate keys on event-hour, not abbreviations, so these helpers
are display-only — a mismatched abbreviation no longer costs a match.

- Abbreviation-emitting books (betr, DraftKings, ESPN) are normalized through
  :data:`TEAM_ABBR_ALIASES` via :func:`canonicalize_team_abbr` so every
  ``AWAY@HOME`` display string converges regardless of source book.
- FanDuel exposes only full team names (no abbreviations), so its ``game`` string
  is built from :data:`TEAM_FULL_NAME_TO_ABBR` via :func:`game_key_from_full_names`.

Both maps target the same canonical (betr) vocabulary so displayed games align.
"""

from __future__ import annotations

import re

# Deviating book abbreviation -> canonical (betr) abbreviation. Verified live
# 2026-06-22: DK uses CWS/PHO/WAS and ESPN uses CWS where betr uses CHW/PHX/WSH.
# Extend here (never per-book) when a new deviation surfaces.
TEAM_ABBR_ALIASES: dict[str, str] = {
    "CWS": "CHW",  # Chicago White Sox — DK/ESPN say CWS, betr says CHW
    "PHO": "PHX",  # Phoenix Mercury — DK says PHO, betr says PHX
    "WAS": "WSH",  # Washington Nationals/Mystics — DK says WAS, betr says WSH
}


def canonicalize_team_abbr(abbr: str) -> str:
    """Normalize a single team abbreviation to the canonical (betr) form."""
    code = abbr.strip().upper()
    return TEAM_ABBR_ALIASES.get(code, code)


# Full team name -> canonical (betr) abbreviation. FanDuel league events carry
# only full names (e.g. "Chicago White Sox"), sometimes with a pitcher annotation
# ("Minnesota Twins (J Ryan)") that is stripped before lookup. Values must match
# betr's vocabulary; abbreviations marked (unverified) are best-standard guesses
# pending a live betr slate carrying that team — a wrong/missing entry only drops
# FanDuel matches for that team (graceful) and never affects DK/ESPN.
TEAM_FULL_NAME_TO_ABBR: dict[str, str] = {
    # --- MLB ---
    "Arizona Diamondbacks": "ARI",
    "Athletics": "ATH",  # (unverified) Sacramento/Oakland Athletics
    "Oakland Athletics": "ATH",  # (unverified)
    "Sacramento Athletics": "ATH",  # (unverified)
    "Atlanta Braves": "ATL",
    "Baltimore Orioles": "BAL",
    "Boston Red Sox": "BOS",
    "Chicago Cubs": "CHC",
    "Chicago White Sox": "CHW",
    "Cincinnati Reds": "CIN",
    "Cleveland Guardians": "CLE",
    "Colorado Rockies": "COL",
    "Detroit Tigers": "DET",
    "Houston Astros": "HOU",
    "Kansas City Royals": "KC",
    "Los Angeles Angels": "LAA",
    "Los Angeles Dodgers": "LAD",
    "Miami Marlins": "MIA",
    "Milwaukee Brewers": "MIL",
    "Minnesota Twins": "MIN",
    "New York Mets": "NYM",
    "New York Yankees": "NYY",
    "Philadelphia Phillies": "PHI",
    "Pittsburgh Pirates": "PIT",
    "San Diego Padres": "SD",
    "San Francisco Giants": "SF",  # (unverified)
    "Seattle Mariners": "SEA",
    "St. Louis Cardinals": "STL",
    "Tampa Bay Rays": "TB",
    "Texas Rangers": "TEX",
    "Toronto Blue Jays": "TOR",
    "Washington Nationals": "WSH",
    # --- WNBA ---
    "Atlanta Dream": "ATL",
    "Chicago Sky": "CHI",
    "Connecticut Sun": "CONN",
    "Dallas Wings": "DAL",
    "Golden State Valkyries": "GSV",  # (unverified)
    "Indiana Fever": "IND",
    "Las Vegas Aces": "LV",
    "Los Angeles Sparks": "LA",  # (unverified)
    "Minnesota Lynx": "MIN",
    "New York Liberty": "NY",
    "Phoenix Mercury": "PHX",
    "Seattle Storm": "SEA",
    "Washington Mystics": "WSH",
}

# Punctuation/case-insensitive lookup so "St. Louis" vs "St Louis" still resolves.
_PAREN_RE = re.compile(r"\s*\([^)]*\)")


def _normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()


_NORMALIZED_NAME_TO_ABBR: dict[str, str] = {
    _normalize_name(name): abbr for name, abbr in TEAM_FULL_NAME_TO_ABBR.items()
}


def abbr_from_full_name(name: str) -> str | None:
    """Resolve a full team name (pitcher annotation stripped) to its canonical abbr."""
    cleaned = _PAREN_RE.sub("", name or "").strip()
    return _NORMALIZED_NAME_TO_ABBR.get(_normalize_name(cleaned))


def game_key_from_full_names(away: str, home: str) -> str | None:
    """Build the ``AWAY@HOME`` canonical key from two full team names, or None."""
    away_abbr = abbr_from_full_name(away)
    home_abbr = abbr_from_full_name(home)
    if away_abbr and home_abbr:
        return f"{away_abbr}@{home_abbr}"
    return None
