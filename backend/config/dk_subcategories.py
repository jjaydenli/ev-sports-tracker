"""DraftKings subcategory IDs and markets URL builders.

DK uses ``subCategoryId`` at two layers (same API name, different scope):

- **Slate** (``slate_subcategory_id``): league landing page — lists scheduled
  games via ``league/leagueSubcategory/v1/markets`` (``DK_LEAGUE_SLATES``).
- **Prop** (``prop_subcategory_id``): per-event stat tab — player props via
  ``event/eventSubcategory/v1/markets`` (the ``DK_*`` id maps below).

Prop tabs vary on two independent axes, so each league carries up to four id
maps (the ``pregame``/``live`` x ``ou``/``milestone`` grid):

- **game state** — pregame vs live (in-play). DK reissues a different
  ``subCategoryId`` for the same market once a game turns live.
- **line kind** — O/U (two-sided over/under) vs milestone (over-only ``N+``
  thresholds, e.g. "2+ hits"). Distinct tabs, distinct ids.

``DK_SUBCATEGORIES`` is the per-league registry; read it via
``subcategories_for_league``. Markets DK lists but we have not mapped an id for
yet live in ``pending`` (not as ``None`` inside an O/U map). Period props
(1st-quarter, 1st-half, ...) are a further DK axis we do not model — there is no
captured data for them; add a grid dimension only when a probe produces ids.

Master board rows keep ``subcategory_id`` to mirror DK market JSON.

Canonical market keys follow the batting_/pitching_ naming convention in
``config/market_maps.py`` for any stat that exists on both sides of the ball
(e.g. ``batting_strikeouts`` vs ``pitching_strikeouts``).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import quote

from config.api_headers import DK_LEAGUE_EVENTS_URL, DK_MARKETS_URL

# --- Prop subCategoryId maps (the raw id data; the registry references these) --

# Canonical market -> DK prop subCategoryId (per-event O/U tabs, NBA pregame).
# Verify: python -m scripts.verify_dk_subcategories --event-id <event_id> --league nba
DK_NBA_PREGAME_STAT_CATEGORIES: dict[str, str] = {
    "points": "12488",
    "rebounds": "12492",
    "assists": "12495",
    "pra": "5001",
    "pts+reb": "9976",
    "pts+ast": "9973",
    "reb+ast": "9974",
    "threes": "12497",
    "steals": "2713508",
    "blocks": "2713780",
    "stl+blk": "2713781",
}

# Over-only milestone prop tabs (1+, 2+, 3+, NBA pregame). Read ids off DevTools,
# then confirm each:
#   python -m scripts.verify_dk_subcategories --event-id <event_id> --verify <id> [<id> ...]
# Only include IDs confirmed against DK market names (not sequential guesses).
# stl+blk: O/U only on DK — no milestone tab observed.
DK_NBA_PREGAME_MILESTONE_STAT_CATEGORIES: dict[str, str] = {
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

# Betr markets awaiting DK prop subCategoryId discovery (None = skip scrape, NBA).
DK_NBA_PENDING_STAT_CATEGORIES: dict[str, str | None] = {
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

# WNBA per-event prop tabs match NBA subCategoryIds (pregame). Live NBA/WNBA
# props do exist on DK; their live ids are just unprobed, so the live maps below
# stay empty until a DevTools capture on an in-progress game fills them.
DK_WNBA_PREGAME_STAT_CATEGORIES: dict[str, str] = DK_NBA_PREGAME_STAT_CATEGORIES
DK_WNBA_PREGAME_MILESTONE_STAT_CATEGORIES: dict[str, str] = DK_NBA_PREGAME_MILESTONE_STAT_CATEGORIES

# MLB player-prop O/U (pregame). Verify:
#   python -m scripts.verify_dk_subcategories --event-id <event_id> --league mlb
DK_MLB_PREGAME_STAT_CATEGORIES: dict[str, str] = {
    "hits": "6719",
    "total_bases": "6607",
    "h+r+rbi": "17406",
    "runs": "17407",
    "singles": "17409",
    "doubles": "17410",
    "batting_walks": "17411",
    "earned_runs": "17412",
    "total_outs": "17413",
    "pitching_strikeouts": "15221",
    "pitching_walks": "15219",
    "hits_allowed": "9886",
    "rbi": "8025",
    # DK-only O/U (no Betr match); stolen_bases confirmed 2026-07-27, h+bb+er closes
    # the pregame/live grid asymmetry with live 19913.
    "stolen_bases": "17408",
    "h+bb+er": "19459",
}

# MLB batter O/U props for live events (subCategoryIds differ from pregame on many tabs).
# Leave None to skip that market for live scrape.
# Verify pregame: python -m scripts.verify_dk_subcategories --event-id <event_id> --league mlb
# Verify live (in-game): ... --league mlb --live  (pregame IDs are wrong for live)
DK_MLB_LIVE_STAT_CATEGORIES: dict[str, str | None] = {
    "hits": "9502",
    "total_bases": "9506",
    "h+r+rbi": "12152",
    "runs": "17475",
    "singles": "17471",
    "doubles": "17472",
    "batting_walks": "9536",
    "rbi": "9505",
    # Pitcher live O/U: verified live 2026-07-25 (order matches DK's tab order).
    "pitching_strikeouts": "12960",
    "earned_runs": "19874",
    "hits_allowed": "12962",
    "pitching_walks": "12963",
    "total_outs": "17476",
    "h+bb+er": "19913",
    # Batter live O/U confirmed 2026-07-27; distinct from pregame 17408 and live
    # milestone 18775.
    "stolen_bases": "17474",
}

# MLB milestone tabs. Pregame N+ tabs verified 2026-07-27; pitcher markets other
# than strikeouts use "X or Fewer" labels the parser drops, so those ids stay in
# docs/betting_odds/mlb.md (DK-only table), not here. Live batter milestone
# verified 2026-07-23 on KC@DET (34425631).
DK_MLB_PREGAME_MILESTONE_STAT_CATEGORIES: dict[str, str | None] = {
    "home_runs": "17319",
    "hits": "17320",
    "total_bases": "17321",
    "rbi": "17322",
    "stolen_bases": "18726",
    "xbh": "19451",
    "h+r+rbi": "17843",
    "h+r+sb": "19452",
    "h+sb": "19454",
    "h+bb+sb": "19455",
    "r+rbi": "19453",
    "runs": "17844",
    "singles": "17845",
    "doubles": "17846",
    "triples": "17847",
    "batting_walks": "17848",
    "batting_strikeouts": "17849",
    "pitching_strikeouts": "17323",
}
DK_MLB_LIVE_MILESTONE_STAT_CATEGORIES: dict[str, str | None] = {
    "batting_strikeouts": "17490",
    "home_runs": "17482",
    "hits": "17483",
    "total_bases": "17480",
    "rbi": "17479",
    "h+r+rbi": "18773",
    "stolen_bases": "18775",
    "batting_walks": "18774",
    "runs": "17488",
    "singles": "17485",
    "doubles": "17486",
    "triples": "17487",
    # Sole live N+ pitcher milestone; five combo batter keys and total_outs have
    # no live milestone tab (confirmed absent 2026-07-27).
    "pitching_strikeouts": "17481",
}


# --- Registry: per-league view over the state x kind grid -------------------


@dataclass(frozen=True)
class PropTabs:
    """Prop subCategoryIds for one game state, split by line kind.

    ``None``/``"TBD"`` values mark markets known on DK but not yet mapped;
    ``configured_*`` drops them so a scrape skips the tab.
    """

    ou: Mapping[str, str | None]
    milestone: Mapping[str, str | None]

    @property
    def configured_ou(self) -> dict[str, str]:
        return _configured(self.ou)

    @property
    def configured_milestone(self) -> dict[str, str]:
        return _configured(self.milestone)


@dataclass(frozen=True)
class LeagueSubcategories:
    """Every prop-id map for one league across the pregame/live x ou/milestone grid."""

    pregame: PropTabs
    live: PropTabs
    pending: Mapping[str, str | None]


def _configured(tabs: Mapping[str, str | None]) -> dict[str, str]:
    """Drop unmapped placeholders (None / ``"TBD"``); keep resolved ids only."""
    return {market: sid for market, sid in tabs.items() if sid and sid != "TBD"}


_NBA = LeagueSubcategories(
    pregame=PropTabs(ou=DK_NBA_PREGAME_STAT_CATEGORIES, milestone=DK_NBA_PREGAME_MILESTONE_STAT_CATEGORIES),
    live=PropTabs(ou={}, milestone={}),
    pending=DK_NBA_PENDING_STAT_CATEGORIES,
)

DK_SUBCATEGORIES: dict[str, LeagueSubcategories] = {
    "nba": _NBA,
    "wnba": LeagueSubcategories(
        pregame=PropTabs(
            ou=DK_WNBA_PREGAME_STAT_CATEGORIES, milestone=DK_WNBA_PREGAME_MILESTONE_STAT_CATEGORIES
        ),
        live=PropTabs(ou={}, milestone={}),
        pending={},
    ),
    "mlb": LeagueSubcategories(
        pregame=PropTabs(
            ou=DK_MLB_PREGAME_STAT_CATEGORIES, milestone=DK_MLB_PREGAME_MILESTONE_STAT_CATEGORIES
        ),
        live=PropTabs(
            ou=DK_MLB_LIVE_STAT_CATEGORIES, milestone=DK_MLB_LIVE_MILESTONE_STAT_CATEGORIES
        ),
        pending={},
    ),
}

DEFAULT_DK_LEAGUE = "nba"


def _registry_tabs() -> list[tuple[str, str, str, str]]:
    """Yield ``(state, kind, market, subcategory_id)`` for every configured prop tab."""
    tabs: list[tuple[str, str, str, str]] = []
    for subs in DK_SUBCATEGORIES.values():
        for state_name, state_tabs in (("pregame", subs.pregame), ("live", subs.live)):
            for kind, configured in (
                ("ou", state_tabs.configured_ou),
                ("milestone", state_tabs.configured_milestone),
            ):
                for market, sid in configured.items():
                    tabs.append((state_name, kind, market, sid))
    return tabs


def subcategory_market_labels() -> dict[str, str]:
    """Map prop ``subCategoryId`` to a log label (e.g. ``pregame:ou:hits``)."""
    labels: dict[str, str] = {}
    for state, kind, market, sid in _registry_tabs():
        labels[sid] = f"{state}:{kind}:{market}"
    return labels


def subcategories_for_league(league: str) -> LeagueSubcategories:
    """Return the prop-id grid for a DK slate key (unknown league -> NBA)."""
    return DK_SUBCATEGORIES.get(league.lower(), DK_SUBCATEGORIES[DEFAULT_DK_LEAGUE])


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
    "wnba": {
        "league_id": "94682",
        "slate_subcategory_id": "4511",
    },
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
