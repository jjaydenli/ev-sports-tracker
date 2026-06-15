"""DraftKings subcategory IDs and markets URL builders.

DK uses ``subCategoryId`` at two layers (same API name, different scope):

- **Slate** (``slate_subcategory_id``): league landing page — lists scheduled
  games via ``league/leagueSubcategory/v1/markets`` (``DK_LEAGUE_SLATES``).
- **Prop** (``prop_subcategory_id``): per-event stat tab — player props via
  ``event/eventSubcategory/v1/markets`` (``DK_*_STAT_CATEGORIES`` maps).

Master board rows keep ``subcategory_id`` to mirror DK market JSON.
"""

from urllib.parse import quote

from config.api_headers import DK_LEAGUE_EVENTS_URL, DK_MARKETS_URL

# Canonical market -> DK prop subCategoryId (per-event O/U tabs).
# Probe: python -m scripts.probe_dk_subcategories <event_id> [--league mlb]
DK_CORE_STAT_CATEGORIES: dict[str, str] = {
    "points": "12488",
    "rebounds": "12492",
    "assists": "12495",
    "pra": "5001",
    "pts+reb": "9976",
    "pts+ast": "9973",
    "reb+ast": "9974",
}

# Confirmed O/U prop subcategories beyond core (NBA).
DK_OU_EXTENDED_STAT_CATEGORIES: dict[str, str] = {
    "threes": "12497",
    "steals": "2713508",
    "blocks": "2713780",
    "stl+blk": "2713781",
}

# Backward-compatible alias for extended O/U stats.
DK_EXTENDED_STAT_CATEGORIES: dict[str, str] = DK_OU_EXTENDED_STAT_CATEGORIES

# Over-only milestone prop tabs (1+, 2+, 3+). Verify with:
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

# Betr markets awaiting DK prop subCategoryId discovery (None = skip scrape).
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

# MLB player-prop O/U (pregame). Verify:
#   python -m scripts.probe_dk_subcategories <event_id> --league mlb
DK_MLB_STAT_CATEGORIES: dict[str, str] = {
    "hits": "6719",
    "total_bases": "6607",
    "h+r+rbi": "17406",
    "runs": "17407",
    "singles": "17409",
    "walks": "17411",
    "earned_runs": "17412",
    "total_outs": "17413",
    "strikeouts": "15221",
    "pitching_walks": "15219",
    "hits_allowed": "9886",
    "rbi": "8025",
}

# Milestone refs for v2 / flat-push (not scraped in v1 full slate)
DK_MLB_MILESTONE_STAT_CATEGORIES: dict[str, str] = {}

# League slate pages for discovering event IDs (game list gateway).
DK_LEAGUE_SLATES: dict[str, dict[str, str]] = {
    "nba": {
        "league_id": "42648",
        "slate_subcategory_id": "4511",
    },
    "mlb": {
        "league_id": "84240",
        "slate_subcategory_id": "4519",
    },
}


def stat_categories_for_league(league: str) -> dict[str, str]:
    """Return canonical market -> prop subCategoryId map for a DK slate key."""
    key = league.lower()
    if key == "mlb":
        return DK_MLB_STAT_CATEGORIES
    return DK_STAT_CATEGORIES


def milestone_categories_for_league(league: str) -> dict[str, str]:
    """Return milestone prop subCategoryId map for a DK slate key."""
    key = league.lower()
    if key == "mlb":
        return DK_MLB_MILESTONE_STAT_CATEGORIES
    return DK_MILESTONE_STAT_CATEGORIES


def configured_stat_categories_for_league(league: str) -> dict[str, str]:
    """Prop subcategories with a resolved ID (excludes TBD placeholders)."""
    return {
        market: sid
        for market, sid in stat_categories_for_league(league).items()
        if sid and sid != "TBD"
    }


def build_markets_query(event_id: str, prop_subcategory_id: str) -> str:
    """Build the OData filter DK expects in marketsQuery for event props."""
    return (
        f"$filter=eventId eq '{event_id}' "
        f"AND clientMetadata/subCategoryId eq '{prop_subcategory_id}' "
        f"AND tags/all(t: t ne 'SportcastBetBuilder')"
    )


def build_league_events_query(league_id: str, slate_subcategory_id: str) -> str:
    """Build the OData filter DK expects in eventsQuery for a league slate."""
    return (
        f"$filter=leagueId eq '{league_id}' "
        f"AND clientMetadata/Subcategories/any(s: s/Id eq '{slate_subcategory_id}')"
    )


def build_league_markets_query(slate_subcategory_id: str) -> str:
    """Build marketsQuery for the league slate request (game-line bundle)."""
    return (
        f"$filter=clientMetadata/subCategoryId eq '{slate_subcategory_id}' "
        f"AND tags/all(t: t ne 'SportcastBetBuilder')"
    )


def build_markets_url(
    event_id: str,
    prop_subcategory_id: str,
    *,
    batchable: bool = False,
) -> str:
    """Build a full event markets API URL for one prop subcategory."""
    markets_query = build_markets_query(event_id, prop_subcategory_id)
    batchable_param = "true" if batchable else "false"
    return (
        f"{DK_MARKETS_URL}?isBatchable={batchable_param}"
        f"&templateVars={event_id},{prop_subcategory_id}"
        f"&marketsQuery={quote(markets_query)}"
        f"&entity=markets"
    )


def build_league_events_url(
    league_id: str,
    slate_subcategory_id: str,
    *,
    batchable: bool = False,
) -> str:
    """Build the league slate URL that returns events for a league page."""
    batchable_param = "true" if batchable else "false"
    return (
        f"{DK_LEAGUE_EVENTS_URL}?isBatchable={batchable_param}"
        f"&templateVars={league_id},{slate_subcategory_id}"
        f"&eventsQuery={quote(build_league_events_query(league_id, slate_subcategory_id))}"
        f"&marketsQuery={quote(build_league_markets_query(slate_subcategory_id))}"
        f"&include=Events&entity=events"
    )
