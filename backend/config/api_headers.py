"""Platform-specific endpoints, user-agents, and request headers."""

import os

from config.espn_queries import ESPN_APP_VERSION

DABBLE_AUTH_URL = "https://api.dabble.com/sign-in"
DABBLE_SCHEDULE_URL = (
    "https://api.dabble.com/search/dfs/competitions/"
    "2acf8935-8d89-455b-bb4b-dbfba9c4ae3b/props?marketGroupName=Points"
)
DABBLE_FIXTURE_DETAIL_URL = (
    "https://api.dabble.com/frontend-api/sport-fixtures/details/{game_id}?filter=dfs-enabled"
)

DABBLE_BASE_HEADERS = {
    "User-Agent": "Dabble/1000041401 CFNetwork/3860.400.51 Darwin/25.3.0",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

DK_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DK_MARKETS_URL = (
    "https://sportsbook-nash.draftkings.com/sites/US-SB/api/sportscontent/"
    "controldata/event/eventSubcategory/v1/markets"
)
DK_LEAGUE_EVENTS_URL = (
    "https://sportsbook-nash.draftkings.com/sites/US-SB/api/sportscontent/"
    "controldata/league/leagueSubcategory/v1/markets"
)
DK_BASE_HEADERS = {
    "User-Agent": DK_USER_AGENT,
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://sportsbook.draftkings.com",
    "Referer": "https://sportsbook.draftkings.com/",
    "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
}

# FanDuel sportsbook (state-specific sbapi host; default NJ).
FD_SPORTSBOOK_API_HOST = os.getenv(
    "FD_SPORTSBOOK_API_HOST", "https://sbapi.nj.sportsbook.fanduel.com"
).rstrip("/")
FD_CONTENT_MANAGED_PAGE_PATH = "/api/content-managed-page"
FD_EVENT_PAGE_PATH = "/api/event-page"
# Public web client key (_ak query param); override via env if FD rotates it.
FD_API_KEY = os.getenv("FD_API_KEY", "FhMFpcPWXMeyZxOx")
FD_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
FD_BASE_HEADERS = {
    "User-Agent": FD_USER_AGENT,
    "Accept": "application/json",
    "Referer": "https://sportsbook.fanduel.com/",
}

# ESPN / TheScore Bet (ESPN BET) sportsbook — GraphQL persisted queries (GET).
# Confirmed live 2026-06-22: host below, not api.thescore.bet. See docs/betting_odds/espn.md.
ESPN_SPORTSBOOK_API_HOST = os.getenv(
    "ESPN_SPORTSBOOK_API_HOST", "https://sportsbook.us-default.thescore.bet"
).rstrip("/")
# Persisted-query GET path: /graphql/persisted_queries/<sha256Hash>?operationName=...&variables=...&extensions=...
ESPN_GRAPHQL_PERSISTED_PATH = "/graphql/persisted_queries"
ESPN_ORIGIN = os.getenv("ESPN_ORIGIN", "https://sportsbook.thescore.bet")
ESPN_REFERER = os.getenv("ESPN_REFERER", "https://sportsbook.thescore.bet/")
ESPN_USER_AGENT = os.getenv(
    "ESPN_USER_AGENT",
    (
        "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/149.0.0.0 Mobile Safari/537.36"
    ),
)

# Client-parity headers from the captured GET (espnbet web app). The token and
# x-install-id are injected per request by build_espn_headers().
ESPN_CLIENT_HEADERS: dict[str, str] = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": ESPN_USER_AGENT,
    "Origin": ESPN_ORIGIN,
    "Referer": ESPN_REFERER,
    "apollographql-client-name": "espnbet-espnbet-web",
    "apollographql-client-version": ESPN_APP_VERSION,
    "x-app": "espnbet",
    "x-app-version": ESPN_APP_VERSION,
    "x-client": "espnbet",
    "x-platform": "web",
}


def build_espn_headers(install_id: str, token: str | None = None) -> dict[str, str]:
    """Return ESPN GraphQL request headers for one install id (+ optional JWE token).

    ``Startup`` (the anonymous mint) is the only op called without ``token``; every
    read op carries ``x-anonymous-authorization: Bearer <JWE>``.
    """
    headers = dict(ESPN_CLIENT_HEADERS)
    headers["x-install-id"] = install_id
    if token:
        token = token.strip()
        if not token.lower().startswith("bearer "):
            token = f"Bearer {token}"
        headers["x-anonymous-authorization"] = token
    return headers

BETR_GRAPHQL_URL = "https://api.fantasy.betr.app/graphql"

# App-parity headers from picks.betr.app DevTools (LeagueUpcomingEvents). The API can
# return a pregame-only slate without jurisdiction/channel/fantasy-api-version.
BETR_USER_AGENT = os.getenv(
    "BETR_USER_AGENT",
    (
        "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/149.0.0.0 Mobile Safari/537.36"
    ),
)
BETR_BASE_HEADERS = {
    "Accept": (
        "application/graphql-response+json, application/graphql+json, "
        "application/json, text/event-stream, multipart/mixed"
    ),
    "Content-Type": "application/json",
    "User-Agent": BETR_USER_AGENT,
    "Referer": "https://picks.betr.app/",
    "channel": os.getenv("BETR_CHANNEL", "MOBILE_WEB"),
    "fantasy-api-version": os.getenv("BETR_FANTASY_API_VERSION", "15.0"),
    "fantasy-application-version": os.getenv("BETR_FANTASY_APPLICATION_VERSION", "3.38.6"),
    "jurisdiction": os.getenv("BETR_JURISDICTION", "CA"),
    "promotions-api-version": os.getenv("BETR_PROMOTIONS_API_VERSION", "5.0"),
}
