"""Betr JWT validation and optional Keycloak token refresh."""

from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from scrapers.dfs.betr.betr_api import normalize_bearer_token


def _env(name: str) -> str | None:
    """Read credential env vars at call time (supports tests and token refresh)."""
    value = os.getenv(name)
    return value if value else None

DEFAULT_EXPIRY_WARN_HOURS = 24
TOKEN_CACHE_FILENAME = ".betr_token_cache.json"


class BetrAuthError(RuntimeError):
    """Raised when Betr credentials are missing, expired, or refresh fails."""


@dataclass(frozen=True)
class JwtExpiryStatus:
    """Result of decoding a Betr JWT expiry claim."""

    expires_at: int | None
    is_expired: bool
    expires_within_warn_window: bool
    warn_hours: int


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def decode_jwt_payload(token: str) -> dict[str, Any]:
    """Decode the JWT payload segment without verifying the signature."""
    token = normalize_bearer_token(token)
    parts = token.split(".")
    if len(parts) < 2:
        raise BetrAuthError("invalid JWT: expected header.payload.signature")
    try:
        payload = json.loads(_b64url_decode(parts[1]))
    except (json.JSONDecodeError, ValueError) as exc:
        raise BetrAuthError("invalid JWT payload") from exc
    if not isinstance(payload, dict):
        raise BetrAuthError("invalid JWT payload: expected JSON object")
    return payload


def jwt_expiry_status(
    token: str,
    *,
    warn_hours: int = DEFAULT_EXPIRY_WARN_HOURS,
    now: int | None = None,
) -> JwtExpiryStatus:
    """Inspect JWT exp and whether it is expired or expiring soon."""
    payload = decode_jwt_payload(token)
    exp = payload.get("exp")
    if exp is None:
        return JwtExpiryStatus(
            expires_at=None,
            is_expired=False,
            expires_within_warn_window=False,
            warn_hours=warn_hours,
        )

    expires_at = int(exp)
    current = int(time.time()) if now is None else int(now)
    warn_seconds = warn_hours * 3600
    return JwtExpiryStatus(
        expires_at=expires_at,
        is_expired=current >= expires_at,
        expires_within_warn_window=current >= expires_at - warn_seconds,
        warn_hours=warn_hours,
    )


def validate_betr_token_or_raise(
    token: str,
    *,
    warn_hours: int = DEFAULT_EXPIRY_WARN_HOURS,
) -> None:
    """Fail fast when the Betr JWT is missing, invalid, expired, or expiring soon."""
    if not token or not token.strip():
        raise BetrAuthError(
            "missing BETR_BEARER_TOKEN — set it in config/.env or configure "
            "BETR_USERNAME/BETR_PASSWORD or BETR_REFRESH_TOKEN for auto-refresh"
        )

    status = jwt_expiry_status(token, warn_hours=warn_hours)
    if status.expires_at is None:
        logger.warning("betr JWT has no exp claim; skipping expiry pre-flight")
        return

    if status.is_expired:
        raise BetrAuthError(
            f"BETR_BEARER_TOKEN expired at unix {status.expires_at} — "
            "refresh via docs/betting_odds/betr.md or set BETR_USERNAME/BETR_PASSWORD"
        )

    if status.expires_within_warn_window:
        raise BetrAuthError(
            f"BETR_BEARER_TOKEN expires within {warn_hours}h (unix {status.expires_at}) — "
            "refresh before running the pipeline"
        )


def keycloak_token_url_from_issuer(issuer: str) -> str:
    """Build the OIDC token endpoint from a JWT iss claim."""
    issuer = issuer.rstrip("/")
    return f"{issuer}/protocol/openid-connect/token"


def resolve_keycloak_token_url(token: str | None = None) -> str | None:
    """Resolve Keycloak token URL from env or JWT iss claim."""
    if _env("BETR_KEYCLOAK_TOKEN_URL"):
        return _env("BETR_KEYCLOAK_TOKEN_URL")

    candidate = token or _env("BETR_BEARER_TOKEN") or ""
    if not candidate:
        return None

    try:
        payload = decode_jwt_payload(candidate)
    except BetrAuthError:
        return None

    issuer = payload.get("iss")
    if isinstance(issuer, str) and issuer:
        return keycloak_token_url_from_issuer(issuer)
    return None


def token_cache_path(data_dir: Path | str = "data/processed") -> Path:
    """Return the gitignored path for cached Betr tokens."""
    return Path(data_dir) / TOKEN_CACHE_FILENAME


def load_token_cache(data_dir: Path | str = "data/processed") -> dict[str, Any] | None:
    """Load cached access/refresh tokens if present."""
    path = token_cache_path(data_dir)
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(f"could not read betr token cache at {path}: {exc}")
        return None
    return data if isinstance(data, dict) else None


def save_token_cache(
    access_token: str,
    *,
    refresh_token: str | None = None,
    data_dir: Path | str = "data/processed",
) -> None:
    """Persist tokens under data/processed (gitignored)."""
    path = token_cache_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {"access_token": normalize_bearer_token(access_token)}
    if refresh_token:
        payload["refresh_token"] = refresh_token
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.environ["BETR_BEARER_TOKEN"] = payload["access_token"]


async def fetch_keycloak_tokens(
    *,
    grant_type: str,
    token_url: str,
    client_id: str,
    client_secret: str | None = None,
    username: str | None = None,
    password: str | None = None,
    refresh_token: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Exchange credentials for Keycloak access (and optional refresh) tokens."""
    data: dict[str, str] = {
        "grant_type": grant_type,
        "client_id": client_id,
    }
    if client_secret:
        data["client_secret"] = client_secret
    if grant_type == "password":
        if not username or not password:
            raise BetrAuthError("password grant requires BETR_USERNAME and BETR_PASSWORD")
        data["username"] = username
        data["password"] = password
    elif grant_type == "refresh_token":
        if not refresh_token:
            raise BetrAuthError("refresh grant requires BETR_REFRESH_TOKEN")
        data["refresh_token"] = refresh_token
    else:
        raise BetrAuthError(f"unsupported grant_type: {grant_type}")

    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient()

    try:
        response = await client.post(
            token_url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15.0,
        )
        response.raise_for_status()
        body = response.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500]
        raise BetrAuthError(
            f"keycloak token request failed: {exc.response.status_code} — {detail}"
        ) from exc
    except httpx.RequestError as exc:
        raise BetrAuthError(f"keycloak token request failed: {exc}") from exc
    finally:
        if owns_client:
            await client.aclose()

    if not isinstance(body, dict) or not body.get("access_token"):
        raise BetrAuthError("keycloak response missing access_token")

    return body


async def login_with_password(
    *,
    token_url: str | None = None,
    client_id: str | None = None,
    data_dir: Path | str = "data/processed",
) -> str:
    """Obtain a Betr access token via Keycloak password grant."""
    resolved_url = token_url or resolve_keycloak_token_url()
    if not resolved_url:
        raise BetrAuthError(
            "set BETR_KEYCLOAK_TOKEN_URL or provide a JWT with iss for auto-discovery"
        )

    resolved_client = client_id or _env("BETR_KEYCLOAK_CLIENT_ID")
    if not resolved_client:
        raise BetrAuthError("set BETR_KEYCLOAK_CLIENT_ID for password grant login")

    body = await fetch_keycloak_tokens(
        grant_type="password",
        token_url=resolved_url,
        client_id=resolved_client,
        username=_env("BETR_USERNAME"),
        password=_env("BETR_PASSWORD"),
    )
    access_token = normalize_bearer_token(body["access_token"])
    save_token_cache(
        access_token,
        refresh_token=body.get("refresh_token"),
        data_dir=data_dir,
    )
    logger.success("obtained fresh Betr access token via password grant")
    return access_token


async def refresh_access_token(
    *,
    refresh_token: str | None = None,
    token_url: str | None = None,
    client_id: str | None = None,
    data_dir: Path | str = "data/processed",
) -> str:
    """Refresh Betr access token via Keycloak refresh_token grant."""
    resolved_url = token_url or resolve_keycloak_token_url(refresh_token)
    if not resolved_url:
        raise BetrAuthError(
            "set BETR_KEYCLOAK_TOKEN_URL or provide a JWT with iss for auto-discovery"
        )

    resolved_client = client_id or _env("BETR_KEYCLOAK_CLIENT_ID")
    if not resolved_client:
        raise BetrAuthError("set BETR_KEYCLOAK_CLIENT_ID for refresh grant")

    token = refresh_token or _env("BETR_REFRESH_TOKEN")
    if not token:
        cache = load_token_cache(data_dir)
        if cache:
            token = cache.get("refresh_token")

    if not token:
        raise BetrAuthError("missing BETR_REFRESH_TOKEN for refresh grant")

    body = await fetch_keycloak_tokens(
        grant_type="refresh_token",
        token_url=resolved_url,
        client_id=resolved_client,
        refresh_token=token,
    )
    access_token = normalize_bearer_token(body["access_token"])
    save_token_cache(
        access_token,
        refresh_token=body.get("refresh_token") or token,
        data_dir=data_dir,
    )
    logger.success("refreshed Betr access token")
    return access_token


async def ensure_betr_token(
    *,
    warn_hours: int = DEFAULT_EXPIRY_WARN_HOURS,
    data_dir: Path | str = "data/processed",
    skip_expiry_check: bool = False,
) -> str:
    """
    Return a valid Betr JWT, refreshing or logging in when configured.

    Order: valid cache → valid BETR_BEARER_TOKEN → refresh grant → password grant.
    """
    cache = load_token_cache(data_dir)
    if cache and cache.get("access_token"):
        cached = normalize_bearer_token(str(cache["access_token"]))
        try:
            if not skip_expiry_check:
                validate_betr_token_or_raise(cached, warn_hours=warn_hours)
            return cached
        except BetrAuthError:
            logger.info("cached Betr token expired or expiring soon; attempting refresh")

    bearer = _env("BETR_BEARER_TOKEN")
    if bearer:
        token = normalize_bearer_token(bearer)
        try:
            if not skip_expiry_check:
                validate_betr_token_or_raise(token, warn_hours=warn_hours)
            return token
        except BetrAuthError:
            logger.info("BETR_BEARER_TOKEN expired or expiring soon; attempting refresh")

    if _env("BETR_REFRESH_TOKEN") or (cache and cache.get("refresh_token")):
        return await refresh_access_token(data_dir=data_dir)

    if _env("BETR_USERNAME") and _env("BETR_PASSWORD"):
        return await login_with_password(data_dir=data_dir)

    raise BetrAuthError(
        "no valid Betr token — set BETR_BEARER_TOKEN or configure refresh/password credentials"
    )
