from config.api_headers import (
    DABBLE_AUTH_URL,
    DABBLE_BASE_HEADERS,
    DABBLE_FIXTURE_DETAIL_URL,
    DABBLE_SCHEDULE_URL,
    DK_BASE_HEADERS,
)
from config.market_maps import DABBLE_MARKET_MAP, DK_MARKET_MAP
from config.settings import DABBLE_PASSWORD, DABBLE_USERNAME

__all__ = [
    "DABBLE_AUTH_URL",
    "DABBLE_BASE_HEADERS",
    "DABBLE_FIXTURE_DETAIL_URL",
    "DABBLE_SCHEDULE_URL",
    "DABBLE_PASSWORD",
    "DABBLE_USERNAME",
    "DABBLE_MARKET_MAP",
    "DK_BASE_HEADERS",
    "DK_MARKET_MAP",
    "MARKET_MAPPING",
]

# Backward-compatible alias used by existing code paths
MARKET_MAPPING = DABBLE_MARKET_MAP
