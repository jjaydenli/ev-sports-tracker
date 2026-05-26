"""DraftKings NBA player-prop subcategory IDs and markets URL builders."""

from urllib.parse import quote

from config.api_headers import DK_LEAGUE_EVENTS_URL, DK_MARKETS_URL

# Canonical market name -> DraftKings subCategoryId (event player props).
# Probe per slate: python -m scripts.probe_dk_subcategories (or league markets URL).
DK_CORE_STAT_CATEGORIES: dict[str, str] = {
    "points": "12488",
    "rebounds": "12492",
    "assists": "12495",
    "pra": "5001",
    "pts+reb": "9976",
    "pts+ast": "9973",
    "reb+ast": "9974",
}

# Confirmed O/U subcategories beyond core (NBA).
DK_OU_EXTENDED_STAT_CATEGORIES: dict[str, str] = {
    "threes": "12497",
    "steals": "2713508",
    "blocks": "2713780",
    "stl+blk": "2713781",
}

# Backward-compatible alias for extended O/U stats.
DK_EXTENDED_STAT_CATEGORIES: dict[str, str] = DK_OU_EXTENDED_STAT_CATEGORIES

# Over-only milestone tabs (1+, 2+, 3+). Verify with:
#   python -m scripts.probe_dk_subcategories <event_id> --discover-milestones
# Only include IDs confirmed against DK market names (not sequential guesses).
# stl+blk: O/U only on DK — no milestone tab observed.
DK_MILESTONE_STAT_CATEGORIES: dict[str, str] = {
    "points": "2716477",
    "rebounds": "2716479",
    "assists": "2716478",
    "threes": "2716480",
    "pts+reb": "2716482",
    "pts+ast": "2716481",
    "reb+ast": "2719560",
    "pra": "2716483",
    "blocks": "2716484",
    "steals": "2716485",
}

# Betr markets awaiting DK subCategoryId discovery (None = skip scrape).
DK_PENDING_STAT_CATEGORIES: dict[str, str | None] = {
    "turnovers": None,
    "fouls": None,
    "fg_attempted": None,
    "fg_made": None,
    "ft_made": None,
    "ft_attempted": None,
    "fantasy_pts": None,
    "3pt_att": None,
    "double-double": None,
    "triple-double": None,
}

DK_STAT_CATEGORIES: dict[str, str] = {
    **DK_CORE_STAT_CATEGORIES,
    **DK_OU_EXTENDED_STAT_CATEGORIES,
}

# League slate pages (e.g. NBA odds) for discovering event IDs
DK_LEAGUE_SLATES: dict[str, dict[str, str]] = {
    "nba": {
        "league_id": "42648",
        "subcategory_id": "4511",
    },
}


def build_markets_query(event_id: str, subcategory_id: str) -> str:
    """Build the OData filter DK expects in marketsQuery for event props."""
    return (
        f"$filter=eventId eq '{event_id}' "
        f"AND clientMetadata/subCategoryId eq '{subcategory_id}' "
        f"AND tags/all(t: t ne 'SportcastBetBuilder')"
    )


def build_league_events_query(league_id: str, subcategory_id: str) -> str:
    """Build the OData filter DK expects in eventsQuery for a league slate."""
    return (
        f"$filter=leagueId eq '{league_id}' "
        f"AND clientMetadata/Subcategories/any(s: s/Id eq '{subcategory_id}')"
    )


def build_league_markets_query(subcategory_id: str) -> str:
    """Build marketsQuery for the league slate request."""
    return (
        f"$filter=clientMetadata/subCategoryId eq '{subcategory_id}' "
        f"AND tags/all(t: t ne 'SportcastBetBuilder')"
    )


def build_markets_url(
    event_id: str,
    subcategory_id: str,
    *,
    batchable: bool = False,
) -> str:
    """Build a full markets API URL for one event and subcategory."""
    markets_query = build_markets_query(event_id, subcategory_id)
    batchable_param = "true" if batchable else "false"
    return (
        f"{DK_MARKETS_URL}?isBatchable={batchable_param}"
        f"&templateVars={event_id},{subcategory_id}"
        f"&marketsQuery={quote(markets_query)}"
        f"&entity=markets"
    )


def build_league_events_url(
    league_id: str,
    subcategory_id: str,
    *,
    batchable: bool = False,
) -> str:
    """Build the league slate URL that returns events for a league page."""
    batchable_param = "true" if batchable else "false"
    return (
        f"{DK_LEAGUE_EVENTS_URL}?isBatchable={batchable_param}"
        f"&templateVars={league_id},{subcategory_id}"
        f"&eventsQuery={quote(build_league_events_query(league_id, subcategory_id))}"
        f"&marketsQuery={quote(build_league_markets_query(subcategory_id))}"
        f"&include=Events&entity=events"
    )
