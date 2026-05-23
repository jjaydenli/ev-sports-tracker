"""String cleaners and standardizers for cross-platform prop matching."""

import re

PROP_PATTERN = re.compile(
    r"O\s*\|\s*([\d.]+)\s*\|\s*([^\s|]+).*?U\s*\|\s*([\d.]+)\s*\|\s*([^\s|]+)"
)


def normalize_odds_string(raw: str) -> str:
    """Normalize unicode minus signs and strip leading plus signs."""
    return raw.replace("\u2212", "-").replace("+", "")


def parse_dk_points_prop(raw_string: str) -> dict | None:
    """
    Parse a DraftKings points prop string from the market-mapping template.
    Returns a normalized prop dict or None when parsing fails.
    """
    if "PPG" not in raw_string:
        return None

    name_section = raw_string.split("PPG", 1)[0]
    name_parts = [part.strip() for part in name_section.split("|") if part.strip()]
    if not name_parts:
        return None

    match = PROP_PATTERN.search(raw_string)
    if not match:
        return None

    try:
        return {
            "sportsbook": "DraftKings",
            "player": name_parts[-1],
            "market": "points",
            "line": float(match.group(1)),
            "over_odds": int(normalize_odds_string(match.group(2))),
            "under_odds": int(normalize_odds_string(match.group(4))),
        }
    except ValueError:
        return None
