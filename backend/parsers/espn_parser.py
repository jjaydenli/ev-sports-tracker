"""Validate and canonicalize ESPN master board rows."""

from config.market_maps import get_canonical_market

ESPN_SPORTSBOOK = "ESPN"
REQUIRED_LINE_FIELDS = ("line", "over_odds", "under_odds")


def _line_entries(raw_prop: dict) -> list[dict]:
    """Return line-level dicts from a grouped or legacy flat master-board row."""
    lines = raw_prop.get("lines")
    if lines:
        return lines
    if raw_prop.get("line") is not None:
        return [raw_prop]
    return []


def parse_espn_prop(raw_prop: dict) -> dict | None:
    """Validate and normalize a single ESPN line row."""
    player = raw_prop.get("player")
    raw_market = raw_prop.get("market", "")
    line = raw_prop.get("line")
    line_kind = raw_prop.get("line_kind", "ou")

    if not player or raw_market is None or line is None:
        return None
    if raw_prop.get("over_odds") is None or raw_prop.get("under_odds") is None:
        return None

    normalized = {
        "sportsbook": raw_prop.get("sportsbook", ESPN_SPORTSBOOK),
        "player": player,
        "market": get_canonical_market("espn", raw_market),
        "line": float(line),
        "prop_type": raw_prop.get("prop_type", "standard"),
        "over_odds": raw_prop.get("over_odds"),
        "under_odds": raw_prop.get("under_odds"),
        "line_kind": line_kind,
        "is_main_line": bool(raw_prop.get("is_main_line", False)),
        "event_id": raw_prop.get("event_id"),
        "tab": raw_prop.get("tab"),
        "market_id": raw_prop.get("market_id"),
        "market_type": raw_prop.get("market_type"),
    }
    league = raw_prop.get("league")
    if league:
        normalized["league"] = str(league).upper()
    event_start = raw_prop.get("event_start")
    if event_start:
        normalized["event_start"] = str(event_start)
    game = raw_prop.get("game")
    if game:
        normalized["game"] = str(game)
    return normalized


def parse_espn_props(raw_props: list[dict]) -> list[dict]:
    """
    Normalize ESPN master board props into line-level rows.

    Grouped master-board entries (``lines`` ladder per player/market) expand to
    one normalized row per O/U line for ``build_player_market_ladder``.
    """
    normalized: list[dict] = []
    for raw_prop in raw_props:
        base = {
            "sportsbook": raw_prop.get("sportsbook", ESPN_SPORTSBOOK),
            "player": raw_prop.get("player"),
            "market": raw_prop.get("market"),
            "line_kind": raw_prop.get("line_kind", "ou"),
            "event_id": raw_prop.get("event_id"),
            "tab": raw_prop.get("tab"),
        }
        league = raw_prop.get("league")
        if league:
            base["league"] = str(league).upper()
        event_start = raw_prop.get("event_start")
        if event_start:
            base["event_start"] = str(event_start)
        game = raw_prop.get("game")
        if game:
            base["game"] = str(game)
        for line_row in _line_entries(raw_prop):
            merged = {**base, **line_row}
            prop = parse_espn_prop(merged)
            if prop:
                normalized.append(prop)
    return normalized
