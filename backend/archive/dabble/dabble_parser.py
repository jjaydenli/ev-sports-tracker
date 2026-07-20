"""Validate and canonicalize Dabble master board rows (archived platform)."""

from config.market_maps import get_canonical_market

DABBLE_SPORTSBOOK = "Dabble"
REQUIRED_FIELDS = ("player", "market", "line")


def parse_dabble_prop(raw_prop: dict) -> dict | None:
    """Validate and normalize a single Dabble prop row."""
    if not all(raw_prop.get(field) is not None for field in REQUIRED_FIELDS):
        return None

    player = raw_prop.get("player")
    raw_market = raw_prop.get("market", "")
    line = raw_prop.get("line")

    assert line is not None  # REQUIRED_FIELDS guard above already ensures this

    return {
        "sportsbook": raw_prop.get("sportsbook", DABBLE_SPORTSBOOK),
        "player": player,
        "market": get_canonical_market("dabble", raw_market),
        "line": float(line),
        "prop_type": raw_prop.get("prop_type", "standard"),
        "over_odds": raw_prop.get("over_odds"),
        "under_odds": raw_prop.get("under_odds"),
        "raw_multiplier": raw_prop.get("raw_multiplier"),
    }


def parse_dabble_props(raw_props: list[dict]) -> list[dict]:
    """Normalize a list of Dabble master board rows."""
    normalized: list[dict] = []
    for raw_prop in raw_props:
        prop = parse_dabble_prop(raw_prop)
        if prop:
            normalized.append(prop)
    return normalized
