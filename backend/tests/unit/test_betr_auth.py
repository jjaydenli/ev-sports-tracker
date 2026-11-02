import base64
import json
import time
from unittest.mock import AsyncMock

import pytest

from scrapers.dfs.betr.betr_auth import (
    DEFAULT_KEYCLOAK_CLIENT_ID,
    BetrAuthError,
    decode_jwt_payload,
    ensure_betr_token,
    fetch_keycloak_tokens,
    jwt_expiry_status,
    keycloak_token_url_from_issuer,
    load_token_cache,
    resolve_keycloak_client_id,
    resolve_keycloak_token_url_source,
    run_auth_probe,
    save_token_cache,
    validate_betr_token_or_raise,
)


def _make_jwt(payload: dict) -> str:
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "none"}).encode()
    ).decode().rstrip("=")
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"{header}.{body}.signature"


def test_decode_jwt_payload_reads_exp():
    token = _make_jwt({"exp": 4_102_444_800, "sub": "user-1"})
    assert decode_jwt_payload(token)["sub"] == "user-1"


def test_jwt_expiry_status_detects_expired_token():
    past = int(time.time()) - 60
    token = _make_jwt({"exp": past})
    status = jwt_expiry_status(token, warn_hours=24, now=int(time.time()))
    assert status.is_expired
    assert status.expires_within_warn_window


def test_validate_betr_token_or_raise_rejects_expiring_soon():
    soon = int(time.time()) + 3600
    token = _make_jwt({"exp": soon})
    with pytest.raises(BetrAuthError, match="expires within"):
        validate_betr_token_or_raise(token, warn_hours=24)


def test_keycloak_token_url_from_issuer():
    url = keycloak_token_url_from_issuer("https://auth.example.com/realms/betr")
    assert url.endswith("/protocol/openid-connect/token")


def test_resolve_keycloak_token_url_from_jwt_iss(monkeypatch):
    monkeypatch.delenv("BETR_KEYCLOAK_TOKEN_URL", raising=False)
    token = _make_jwt({"iss": "https://auth.example.com/realms/betr", "exp": 9_999_999_999})
    url, source = resolve_keycloak_token_url_source(token)
    assert url == "https://auth.example.com/realms/betr/protocol/openid-connect/token"
    assert source == "jwt:iss (arg)"


def test_resolve_keycloak_token_url_from_cache_access_token(monkeypatch, tmp_path):
    monkeypatch.delenv("BETR_KEYCLOAK_TOKEN_URL", raising=False)
    monkeypatch.delenv("BETR_BEARER_TOKEN", raising=False)
    cached = _make_jwt({"iss": "https://auth.example.com/realms/betr", "exp": 1})
    save_token_cache(cached, refresh_token="refresh-1", data_dir=tmp_path)
    monkeypatch.delenv("BETR_BEARER_TOKEN", raising=False)
    monkeypatch.setattr(
        "scrapers.dfs.betr.betr_auth.load_token_cache",
        lambda *a, **k: load_token_cache(tmp_path),
    )

    url, source = resolve_keycloak_token_url_source()
    assert url == "https://auth.example.com/realms/betr/protocol/openid-connect/token"
    assert source == "jwt:iss (cache:access_token)"


def test_resolve_keycloak_token_url_source_from_env(monkeypatch):
    monkeypatch.setenv("BETR_KEYCLOAK_TOKEN_URL", "https://auth.example.com/token")
    url, source = resolve_keycloak_token_url_source()
    assert url == "https://auth.example.com/token"
    assert source == "env:BETR_KEYCLOAK_TOKEN_URL"


def test_resolve_keycloak_client_id_defaults_to_betr_web(monkeypatch):
    monkeypatch.delenv("BETR_KEYCLOAK_CLIENT_ID", raising=False)
    client_id, source = resolve_keycloak_client_id()
    assert client_id == DEFAULT_KEYCLOAK_CLIENT_ID
    assert source == "default"


def test_resolve_keycloak_client_id_from_env(monkeypatch):
    monkeypatch.setenv("BETR_KEYCLOAK_CLIENT_ID", "custom-client")
    client_id, source = resolve_keycloak_client_id()
    assert client_id == "custom-client"
    assert source == "env:BETR_KEYCLOAK_CLIENT_ID"


@pytest.mark.asyncio
async def test_run_auth_probe_without_credentials(monkeypatch, capsys):
    monkeypatch.delenv("BETR_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("BETR_KEYCLOAK_TOKEN_URL", raising=False)
    monkeypatch.delenv("BETR_KEYCLOAK_CLIENT_ID", raising=False)
    monkeypatch.delenv("BETR_USERNAME", raising=False)
    monkeypatch.delenv("BETR_PASSWORD", raising=False)
    monkeypatch.delenv("BETR_REFRESH_TOKEN", raising=False)
    monkeypatch.setattr("scrapers.dfs.betr.betr_auth.load_token_cache", lambda *a, **k: None)

    exit_code = await run_auth_probe(try_grant=False)
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Betr auth probe" in captured.out
    assert f"client_id: {DEFAULT_KEYCLOAK_CLIENT_ID}" in captured.out
    assert "env_bearer: not configured" in captured.out
    assert "grant_configured: none" in captured.out


@pytest.mark.asyncio
async def test_run_auth_probe_refresh_path_without_env_bearer(monkeypatch, capsys, tmp_path):
    monkeypatch.delenv("BETR_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("BETR_KEYCLOAK_TOKEN_URL", raising=False)
    monkeypatch.setenv("BETR_REFRESH_TOKEN", "refresh-1")
    future = int(time.time()) + 86400 * 30
    cached = _make_jwt({"iss": "https://auth.example.com/realms/betr", "exp": future})
    save_token_cache(cached, refresh_token="refresh-1", data_dir=tmp_path)
    monkeypatch.delenv("BETR_BEARER_TOKEN", raising=False)
    monkeypatch.setattr(
        "scrapers.dfs.betr.betr_auth.load_token_cache",
        lambda *a, **k: load_token_cache(tmp_path),
    )

    exit_code = await run_auth_probe(try_grant=False)
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "env_bearer: not configured (cache/refresh path)" in captured.out
    assert "cache_access_expired: False" in captured.out
    assert "grant_configured: refresh_token" in captured.out


@pytest.mark.asyncio
async def test_fetch_keycloak_tokens_password_grant(monkeypatch):
    mock_response = AsyncMock()
    mock_response.raise_for_status = lambda: None
    mock_response.json = lambda: {"access_token": "fresh-token", "refresh_token": "refresh-1"}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.aclose = AsyncMock()

    monkeypatch.setattr(
        "scrapers.dfs.betr.betr_auth.httpx.AsyncClient",
        lambda: mock_client,
    )

    body = await fetch_keycloak_tokens(
        grant_type="password",
        token_url="https://auth.example.com/realms/betr/protocol/openid-connect/token",
        client_id="betr-web",
        username="user@example.com",
        password="secret",
        client=mock_client,
    )

    assert body["access_token"] == "fresh-token"
    mock_client.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_betr_token_uses_valid_env_token(monkeypatch, tmp_path):
    future = int(time.time()) + 86400 * 30
    token = _make_jwt({"exp": future})
    monkeypatch.setenv("BETR_BEARER_TOKEN", token)
    monkeypatch.delenv("BETR_USERNAME", raising=False)
    monkeypatch.delenv("BETR_REFRESH_TOKEN", raising=False)

    result = await ensure_betr_token(skip_expiry_check=True, data_dir=tmp_path)
    assert result == token


@pytest.mark.asyncio
async def test_ensure_betr_token_password_login_when_expired(monkeypatch, tmp_path):
    past = int(time.time()) - 10
    expired = _make_jwt({"exp": past, "iss": "https://auth.example.com/realms/betr"})
    monkeypatch.setenv("BETR_BEARER_TOKEN", expired)
    monkeypatch.setenv("BETR_USERNAME", "user@example.com")
    monkeypatch.setenv("BETR_PASSWORD", "secret")
    monkeypatch.setenv("BETR_KEYCLOAK_CLIENT_ID", "betr-web")
    monkeypatch.delenv("BETR_REFRESH_TOKEN", raising=False)

    future = int(time.time()) + 86400
    fresh = _make_jwt({"exp": future})

    async def _fake_login(**_kwargs):
        save_token_cache(fresh, refresh_token="new-refresh", data_dir=tmp_path)
        return fresh

    monkeypatch.setattr(
        "scrapers.dfs.betr.betr_auth.login_with_password",
        _fake_login,
    )

    result = await ensure_betr_token(data_dir=tmp_path)
    assert result == fresh


def _dead_refresh_setup(monkeypatch, tmp_path):
    """Expired cached access token plus a refresh token Keycloak has revoked."""
    expired = _make_jwt({"exp": int(time.time()) - 10, "iss": "https://auth.example.com/realms/betr"})
    save_token_cache(expired, refresh_token="revoked-refresh", data_dir=tmp_path)
    monkeypatch.delenv("BETR_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("BETR_REFRESH_TOKEN", raising=False)
    monkeypatch.delenv("BETR_USERNAME", raising=False)
    monkeypatch.delenv("BETR_PASSWORD", raising=False)
    monkeypatch.setenv("BETR_KEYCLOAK_TOKEN_URL", "https://auth.example.com/token")


def _fake_keycloak(fresh: str = ""):
    """Keycloak double: refresh grant is rejected as in the captured 400, password grant works."""

    async def _fetch(*, grant_type, **_kwargs):
        if grant_type == "refresh_token":
            raise BetrAuthError(
                'keycloak token request failed: 400 — {"error":"invalid_grant",'
                '"error_description":"Offline user session not found"}'
            )
        return {"access_token": fresh, "refresh_token": "new-refresh"}

    return _fetch


@pytest.mark.asyncio
async def test_ensure_betr_token_falls_back_to_password_when_refresh_revoked(monkeypatch, tmp_path):
    """Regression: invalid_grant on refresh used to abort the run despite valid username/password."""
    _dead_refresh_setup(monkeypatch, tmp_path)
    monkeypatch.setenv("BETR_USERNAME", "user@example.com")
    monkeypatch.setenv("BETR_PASSWORD", "secret")
    fresh = _make_jwt({"exp": int(time.time()) + 86400})
    monkeypatch.setattr("scrapers.dfs.betr.betr_auth.fetch_keycloak_tokens", _fake_keycloak(fresh))

    assert await ensure_betr_token(data_dir=tmp_path) == fresh
    assert load_token_cache(tmp_path)["refresh_token"] == "new-refresh"


@pytest.mark.asyncio
async def test_ensure_betr_token_revoked_refresh_without_password_explains_fix(monkeypatch, tmp_path):
    _dead_refresh_setup(monkeypatch, tmp_path)
    monkeypatch.setattr("scrapers.dfs.betr.betr_auth.fetch_keycloak_tokens", _fake_keycloak())

    with pytest.raises(BetrAuthError, match=r"Offline user session not found.*BETR_USERNAME"):
        await ensure_betr_token(data_dir=tmp_path)


@pytest.mark.asyncio
async def test_ensure_betr_token_outage_without_password_is_not_called_revoked(monkeypatch, tmp_path):
    """A Keycloak outage leaves the refresh token valid, so don't advise re-capturing it."""
    _dead_refresh_setup(monkeypatch, tmp_path)

    async def _unavailable(**_kwargs):
        raise BetrAuthError("keycloak token request failed: 503 — upstream unavailable")

    monkeypatch.setattr("scrapers.dfs.betr.betr_auth.fetch_keycloak_tokens", _unavailable)

    with pytest.raises(BetrAuthError) as exc:
        await ensure_betr_token(data_dir=tmp_path)

    assert str(exc.value) == "keycloak token request failed: 503 — upstream unavailable"
