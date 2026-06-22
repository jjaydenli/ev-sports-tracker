"""Load local credentials from config/.env or backend/.env."""

import os
from pathlib import Path

from dotenv import load_dotenv

_CONFIG_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _CONFIG_DIR.parent

load_dotenv(_CONFIG_DIR / ".env")
load_dotenv(_BACKEND_DIR / ".env")

DABBLE_USERNAME = os.getenv("DABBLE_USERNAME")
DABBLE_PASSWORD = os.getenv("DABBLE_PASSWORD")
BETR_BEARER_TOKEN = os.getenv("BETR_BEARER_TOKEN")
BETR_USERNAME = os.getenv("BETR_USERNAME")
BETR_PASSWORD = os.getenv("BETR_PASSWORD")
BETR_REFRESH_TOKEN = os.getenv("BETR_REFRESH_TOKEN")
BETR_KEYCLOAK_TOKEN_URL = os.getenv("BETR_KEYCLOAK_TOKEN_URL")
BETR_KEYCLOAK_CLIENT_ID = os.getenv("BETR_KEYCLOAK_CLIENT_ID")


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return float(raw)


# Multi-book consensus weights (equal 1.0 defaults). See core/line_adjustment.py.
SHARP_BOOK_WEIGHTS_DK = _float_env("SHARP_BOOK_WEIGHTS_DK", 1.0)
SHARP_BOOK_WEIGHTS_FD = _float_env("SHARP_BOOK_WEIGHTS_FD", 1.0)
SHARP_BOOK_WEIGHTS_ESPN = _float_env("SHARP_BOOK_WEIGHTS_ESPN", 1.0)

# Milestone (N+) admission gate — fair over prob floor and hold fallback.
MILESTONE_MIN_FAIR_OVER = _float_env("MILESTONE_MIN_FAIR_OVER", 0.6154)  # −160
MILESTONE_ASSUMED_HOLD = _float_env("MILESTONE_ASSUMED_HOLD", 0.06)
