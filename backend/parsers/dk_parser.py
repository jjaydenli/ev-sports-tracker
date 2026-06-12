"""Validate and canonicalize DraftKings master board rows."""

from config.market_maps import get_canonical_market

DK_SPORTSBOOK = "DraftKings"
REQUIRED_FIELDS = ("player", "market", "line")


def parse_dk_prop(raw_prop: dict) -> dict | None:
    """Validate and normalize a single DraftKings prop row."""
    if not all(raw_prop.get(field) is not None for field in REQUIRED_FIELDS):
        return None

    player = raw_prop.get("player")
    raw_market = raw_prop.get("market", "")
    line = raw_prop.get("line")

    normalized = {
        "sportsbook": raw_prop.get("sportsbook", DK_SPORTSBOOK),
        "player": player,
        "market": get_canonical_market("draftkings", raw_market),
        "line": float(line),
        "prop_type": raw_prop.get("prop_type", "standard"),
        "over_odds": raw_prop.get("over_odds"),
        "under_odds": raw_prop.get("under_odds"),
        "line_kind": raw_prop.get("line_kind", "ou"),
        "milestone_threshold": raw_prop.get("milestone_threshold"),
        "is_main_line": bool(raw_prop.get("is_main_line", True)),
        "raw_multiplier": raw_prop.get("raw_multiplier"),
    }
    league = raw_prop.get("league")
    if league:
        normalized["league"] = str(league).upper()
    return normalized


def parse_dk_props(raw_props: list[dict]) -> list[dict]:
    """Normalize a list of DraftKings master board rows."""
    normalized: list[dict] = []
    for raw_prop in raw_props:
        prop = parse_dk_prop(raw_prop)
        if prop:
            normalized.append(prop)
    return normalized
