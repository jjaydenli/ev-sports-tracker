"""Platform-specific endpoints, user-agents, and request headers."""

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
DK_BASE_HEADERS = {"User-Agent": DK_USER_AGENT}

BETR_GRAPHQL_URL = "https://api.fantasy.betr.app/graphql"

BETR_BASE_HEADERS = {
    "Content-Type": "application/json",
}
