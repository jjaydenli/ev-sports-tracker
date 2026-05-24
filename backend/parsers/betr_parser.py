"""
Normalize raw Betr master board rows into shared NormalizedProp records.

V1 includes only REGULAR (standard) projections. Deferred pick-type taxonomy:
- Boost: harder line, higher multiplier (MINI_BOOSTED, BOOSTED, SUPER_BOOSTED)
- Edge: easier line, lower multiplier (EDGE, EDGE_1, EDGE_3)
- Discount / Nuke / Surge / Anchor: promo picks with alternate value/nonRegularValue
"""

from config.market_maps import get_canonical_market

BETR_SPORTSBOOK = "Betr"
BETR_STANDARD_ODDS = -120
STANDARD_PROJECTION_TYPE = "REGULAR"

# TODO: map non-REGULAR types to prop_type and select value vs non_regular_value

def _resolve_betr_market(raw_prop: dict) -> str:
    """Resolve canonical market from Betr key, falling back to label."""
    key = raw_prop.get("key")
    if key:
        return get_canonical_market("betr", key)

    label = raw_prop.get("label")
    if label:
        return get_canonical_market("betr", label)

    return ""


def parse_betr_prop(raw_prop: dict) -> dict | None:
    """Convert a single raw Betr prop into a NormalizedProp-compatible dict."""
    projection_type = raw_prop.get("type")
    if projection_type != STANDARD_PROJECTION_TYPE:
        return None

    player = raw_prop.get("player")
    value = raw_prop.get("value")
    if not player or value is None:
        return None

    market = _resolve_betr_market(raw_prop)
    if not market:
        return None

    normalized = {
        "sportsbook": BETR_SPORTSBOOK,
        "player": player,
        "market": market,
        "line": float(value),
        "prop_type": "standard",
        "over_odds": BETR_STANDARD_ODDS,
        "under_odds": BETR_STANDARD_ODDS,
        "raw_multiplier": None,
    }

    market_id = raw_prop.get("market_id")
    if market_id:
        normalized["source_market_id"] = market_id

    game = raw_prop.get("game")
    if game:
        normalized["game"] = game

    team = raw_prop.get("team")
    if team:
        normalized["team"] = team

    return normalized


def parse_betr_props(raw_props: list[dict]) -> list[dict]:
    """Normalize a list of raw Betr master board rows."""
    normalized: list[dict] = []
    for raw_prop in raw_props:
        prop = parse_betr_prop(raw_prop)
        if prop:
            normalized.append(prop)
    return normalized
