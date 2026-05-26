"""Validate and canonicalize FanDuel master board rows."""

from config.market_maps import get_canonical_market

FD_SPORTSBOOK = "FanDuel"
REQUIRED_FIELDS = ("player", "market", "line")


def parse_fd_prop(raw_prop: dict) -> dict | None:
    """Validate and normalize a single FanDuel prop row."""
    if not all(raw_prop.get(field) is not None for field in REQUIRED_FIELDS):
        return None

    player = raw_prop.get("player")
    raw_market = raw_prop.get("market", "")
    line = raw_prop.get("line")

    return {
        "sportsbook": raw_prop.get("sportsbook", FD_SPORTSBOOK),
        "player": player,
        "market": get_canonical_market("fanduel", raw_market),
        "line": float(line),
        "prop_type": raw_prop.get("prop_type", "standard"),
        "over_odds": raw_prop.get("over_odds"),
        "under_odds": raw_prop.get("under_odds"),
        "line_kind": raw_prop.get("line_kind", "ou"),
        "is_main_line": bool(raw_prop.get("is_main_line", False)),
        "event_id": raw_prop.get("event_id"),
        "tab": raw_prop.get("tab"),
        "market_id": raw_prop.get("market_id"),
        "market_type": raw_prop.get("market_type"),
    }


def parse_fd_props(raw_props: list[dict]) -> list[dict]:
    """Normalize a list of FanDuel master board rows."""
    normalized: list[dict] = []
    for raw_prop in raw_props:
        prop = parse_fd_prop(raw_prop)
        if prop:
            normalized.append(prop)
    return normalized
