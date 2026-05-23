"""Canonical market translations across DFS and sportsbook platforms."""

DABBLE_MARKET_MAP = {
    "points": "points",
    "assists": "assists",
    "rebounds": "rebounds",
    "steals": "steals",
    "blocks": "blocks",
    "turnovers": "turnovers",
    "assists_points_rebounds": "pra",
    "assists_points": "pts+ast",
    "points_rebounds": "pts+reb",
    "assists_rebounds": "reb+ast",
    "blocks_steals": "stl+blk",
    "three_made": "threes",
    "double-double": "double-double",
    "triple-double": "triple-double",
    "fg-attempted": "fg_attempted",
}

DK_MARKET_MAP = {
    "points": "points",
    "rebounds": "rebounds",
    "assists": "assists",
    "threes": "threes",
    "3-pt field goals made": "threes",
    "steals": "steals",
    "blocks": "blocks",
    "steals + blocks": "stl+blk",
    "pts + reb + ast": "pra",
    "pts + reb": "pts+reb",
    "pts + ast": "pts+ast",
    "reb + ast": "reb+ast",
}

PLATFORM_MARKET_MAPPINGS = {
    "dabble": DABBLE_MARKET_MAP,
    "draftkings": DK_MARKET_MAP,
}


def get_canonical_market(platform: str, raw_market: str) -> str:
    """Map a platform-specific market key to the shared canonical name."""
    platform_map = PLATFORM_MARKET_MAPPINGS.get(platform, {})
    return platform_map.get(raw_market, raw_market)
