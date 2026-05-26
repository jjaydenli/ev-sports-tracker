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
