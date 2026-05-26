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

BETR_MARKET_MAP = {
    # display labels
    "points": "points",
    "rebounds": "rebounds",
    "assists": "assists",
    "steals": "steals",
    "blocks": "blocks",
    "turnovers": "turnovers",
    "3-pointers made": "threes",
    "3-pointers": "threes",
    "3pm": "threes",
    "threes": "threes",
    "pts + rebs + asts": "pra",
    "pts + ast": "pts+ast",
    "pts + reb": "pts+reb",
    "pts + rebs": "pts+reb",
    "rebs + asts": "reb+ast",
    "rebs + ast": "reb+ast",
    "steals + blocks": "stl+blk",
    "stl + blk": "stl+blk",
    "double doubles": "double-double",
    "triple doubles": "triple-double",
    "fg att": "fg_attempted",
    "fg made": "fg_made",
    "ft made": "ft_made",
    "ft att": "ft_attempted",
    "fantasy score": "fantasy_pts",
    "fantasy pts": "fantasy_pts",
    "3pt att": "3pt_att",
    "3pt made": "threes",
    "fouls": "fouls",
    # projection keys (GraphQL `key` field)
    "fantasy_points": "fantasy_pts",
    "three_pointers_attempted": "3pt_att",
    "three_pointers_made": "threes",
    "three_pointers": "threes",
    "points_rebounds_assists": "pra",
    "points_rebounds": "pts+reb",
    "points_assists": "pts+ast",
    "rebounds_assists": "reb+ast",
    "assists_rebounds": "reb+ast",
    "steals_blocks": "stl+blk",
    "field_goals_attempted": "fg_attempted",
    "field_goals_made": "fg_made",
    "free_throws_made": "ft_made",
    "free_throws_attempted": "ft_attempted",
    "double_double": "double-double",
    "triple_double": "triple-double",
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
    "stl + blk": "stl+blk",
    "steals & blocks": "stl+blk",
    "pts + reb + ast": "pra",
    "pts + reb": "pts+reb",
    "pts + ast": "pts+ast",
    "reb + ast": "reb+ast",
}

PLATFORM_MARKET_MAPPINGS = {
    "dabble": DABBLE_MARKET_MAP,
    "betr": BETR_MARKET_MAP,
    "draftkings": DK_MARKET_MAP,
    "fanduel": {
        "points": "points",
        "rebounds": "rebounds",
        "assists": "assists",
        "threes": "threes",
        "pts+reb": "pts+reb",
        "pts+ast": "pts+ast",
        "pra": "pra",
        "reb+ast": "reb+ast",
    },
}


def get_canonical_market(platform: str, raw_market: str) -> str:
    """Map a platform-specific market key to the shared canonical name."""
    platform_map = PLATFORM_MARKET_MAPPINGS.get(platform, {})
    normalized = raw_market.strip().lower()
    return platform_map.get(normalized, normalized)
