"""
Normalize raw Betr master board rows into shared NormalizedProp records.

V1 includes only REGULAR (standard) projections. Deferred pick-type taxonomy:
- Boost: harder line, higher multiplier (MINI_BOOSTED, BOOSTED, SUPER_BOOSTED)
- Edge: easier line, lower multiplier (EDGE, EDGE_1, EDGE_3)
- Discount / Nuke / Surge / Anchor: promo picks with alternate value/nonRegularValue
"""

from config.market_maps import get_canonical_market
from core.flat_line import line_kind
from utils.math_utils import BETR_STANDARD_BREAKEVEN_ODDS

BETR_SPORTSBOOK = "Betr"
STANDARD_PROJECTION_TYPE = "REGULAR"
MLB_V1_MARKETS = frozenset({"h+r+rbi", "singles"})

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


def _parse_allowed_sides(allowed_options: list[dict]) -> tuple[bool, bool]:
    """
    Return (over_allowed, under_allowed) from Betr allowedOptions outcomes.

    Betr uses MORE/LESS in addition to OVER/UNDER (same semantics as Dabble).
    """
    over_allowed = False
    under_allowed = False

    for option in allowed_options:
        outcome = (option.get("outcome") or "").strip().upper()
        if outcome in ("OVER", "MORE"):
            over_allowed = True
        elif outcome in ("UNDER", "LESS"):
            under_allowed = True

    return over_allowed, under_allowed


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

    league = (raw_prop.get("league") or "").upper()
    if league == "MLB" and market not in MLB_V1_MARKETS:
        return None

    allowed_options = raw_prop.get("allowed_options") or []
    if not allowed_options:
        return None

    over_allowed, under_allowed = _parse_allowed_sides(allowed_options)
    if not over_allowed and not under_allowed:
        return None

    line = float(value)
    normalized = {
        "sportsbook": BETR_SPORTSBOOK,
        "player": player,
        "market": market,
        "line": line,
        "line_kind": line_kind(line),
        "prop_type": "standard",
        "over_odds": BETR_STANDARD_BREAKEVEN_ODDS if over_allowed else None,
        "under_odds": BETR_STANDARD_BREAKEVEN_ODDS if under_allowed else None,
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

    if league:
        normalized["league"] = league

    event_status = raw_prop.get("event_status")
    if event_status:
        normalized["event_status"] = event_status

    return normalized


def parse_betr_props(raw_props: list[dict]) -> list[dict]:
    """Normalize a list of raw Betr master board rows."""
    normalized: list[dict] = []
    for raw_prop in raw_props:
        prop = parse_betr_prop(raw_prop)
        if prop:
            normalized.append(prop)
    return normalized
