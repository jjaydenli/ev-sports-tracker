"""ESPN (TheScore Bet) anonymous JWE auth — Startup mint + cache (decision 5).

ESPN serves player props behind ``x-anonymous-authorization: Bearer <JWE>``. The token
is minted by the ``Startup`` persisted-query op (GET, **no** bearer) which returns
``data.startup.anonymousToken``. ``connectToken`` and ``x-install-id`` are client-generated
random 23-char ``[a-z0-9]`` ids the server accepts as-is, so the whole flow is programmatic
with zero stored secrets (a static ``ESPN_ANON_TOKEN`` stays rejected).

The token is an **encrypted** JWE (``alg:RSA-OAEP``) with no readable ``exp`` — validity
cannot be introspected like Betr's JWT. So we cache ``(install_id, anonymous_token)`` in
``data/processed/.espn_token_cache.json`` (gitignored), reuse it across runs with a **stable**
install id, and re-mint reactively on a 401/403 (see ``espn_api``). This mirrors the
``ensure_betr_token`` lifecycle, but the refresh trigger is an auth failure, not expiry.
"""

from __future__ import annotations

import json
import os
import random
import string
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

TOKEN_CACHE_FILENAME = ".espn_token_cache.json"
_INSTALL_ID_ALPHABET = string.ascii_lowercase + string.digits
_INSTALL_ID_LEN = 23

# Startup variables — latLongParams.{accuracy,latitude,longitude} are each a required
# non-null GraphQL ``Float!`` (the server rejects ``null`` with VALIDATION_INVALID_TYPE_VARIABLE).
# Zeroed (null-island) coords mint a valid anonymous token against the ``us-default`` region —
# the host the whole pipeline + Phase 0 capture target. Real coordinates instead trip a geo-region
# check (a 302 "not connected to a valid region", pointing at a state-specific host), so we keep
# the mint location-agnostic and pinned to us-default; the anonymous read path needs no real fix.
_STARTUP_LAT_LONG: dict[str, Any] = {
    "accuracy": 0.0,
    "latitude": 0.0,
    "longitude": 0.0,
}


class ESPNAuthError(RuntimeError):
    """Raised when the ESPN anonymous token cannot be minted."""


def _random_id(length: int = _INSTALL_ID_LEN) -> str:
    """Return a random ``[a-z0-9]`` id (server accepts arbitrary ids)."""
    return "".join(random.choices(_INSTALL_ID_ALPHABET, k=length))


def token_cache_path(data_dir: Path | str = "data/processed") -> Path:
    """Return the gitignored path for the cached ESPN install id + token."""
    return Path(data_dir) / TOKEN_CACHE_FILENAME


def load_token_cache(data_dir: Path | str = "data/processed") -> dict[str, Any] | None:
    """Load the cached ``{install_id, anonymous_token}`` if present and readable."""
    path = token_cache_path(data_dir)
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(f"could not read espn token cache at {path}: {exc}")
        return None
    return data if isinstance(data, dict) else None


def save_token_cache(
    install_id: str,
    anonymous_token: str | None,
    *,
    data_dir: Path | str = "data/processed",
) -> None:
    """Persist install id (+ token) under data/processed (gitignored)."""
    path = token_cache_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {"install_id": install_id}
    if anonymous_token:
        payload["anonymous_token"] = anonymous_token
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def ensure_install_id(data_dir: Path | str = "data/processed") -> str:
    """Return a stable install id, generating and persisting one on first use.

    A returning-device identity is gentler on bot detection than a fresh id per run,
    so the install id is reused across runs even when the token is re-minted.
    """
    env_id = os.getenv("ESPN_INSTALL_ID")
    if env_id:
        return env_id
    cache = load_token_cache(data_dir)
    if cache and cache.get("install_id"):
        return str(cache["install_id"])
    install_id = _random_id()
    save_token_cache(install_id, None, data_dir=data_dir)
    return install_id


def _startup_url() -> str:
    from config.api_headers import (
        ESPN_GRAPHQL_PERSISTED_PATH,
        ESPN_SPORTSBOOK_API_HOST,
    )
    from config.espn_queries import persisted_query_hash

    return (
        f"{ESPN_SPORTSBOOK_API_HOST}{ESPN_GRAPHQL_PERSISTED_PATH}/"
        f"{persisted_query_hash('Startup')}"
    )


async def mint_anonymous_token(
    install_id: str,
    *,
    client: httpx.AsyncClient,
) -> str:
    """Call the ``Startup`` persisted query (no bearer) → ``anonymousToken`` (JWE)."""
    from config.api_headers import build_espn_headers
    from config.espn_queries import persisted_query_extensions

    variables = {
        "connectToken": _random_id(),
        "latLongParams": _STARTUP_LAT_LONG,
    }
    params = {
        "operationName": "Startup",
        "variables": json.dumps(variables, separators=(",", ":")),
        "extensions": persisted_query_extensions("Startup"),
    }
    try:
        response = await client.get(
            _startup_url(),
            params=params,
            headers=build_espn_headers(install_id),  # no token: anonymous mint
            timeout=15.0,
        )
        response.raise_for_status()
        body = response.json()
    except httpx.HTTPStatusError as exc:
        raise ESPNAuthError(
            f"espn Startup mint failed: {exc.response.status_code} — "
            f"{exc.response.text[:300]}"
        ) from exc
    except httpx.RequestError as exc:
        raise ESPNAuthError(f"espn Startup mint request failed: {exc}") from exc

    token = ((body or {}).get("data") or {}).get("startup", {}).get("anonymousToken")
    if not token:
        raise ESPNAuthError("espn Startup response missing data.startup.anonymousToken")
    return str(token)


async def ensure_espn_token(
    *,
    client: httpx.AsyncClient | None = None,
    force_refresh: bool = False,
    data_dir: Path | str = "data/processed",
) -> tuple[str, str]:
    """Return ``(install_id, anonymous_token)``, minting via Startup when needed.

    Order: reuse cached token (stable install id) → mint on miss or ``force_refresh``.
    Call with ``force_refresh=True`` after a 401/403 to re-mint with the same install id.
    """
    install_id = ensure_install_id(data_dir)
    cache = load_token_cache(data_dir)
    if not force_refresh and cache and cache.get("anonymous_token"):
        return install_id, str(cache["anonymous_token"])

    owns_client = client is None
    if owns_client:
        from config.api_headers import ESPN_CLIENT_HEADERS

        http_client = httpx.AsyncClient(headers=ESPN_CLIENT_HEADERS, follow_redirects=True)
    else:
        assert client is not None
        http_client = client
    try:
        token = await mint_anonymous_token(install_id, client=http_client)
    finally:
        if owns_client:
            await http_client.aclose()

    save_token_cache(install_id, token, data_dir=data_dir)
    logger.success("minted fresh ESPN anonymous token via Startup")
    return install_id, token
