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
