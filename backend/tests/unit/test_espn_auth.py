"""ESPN auth offline unit tests — cache/expiry/id paths only; no network calls."""

from __future__ import annotations

import json

from scrapers.sportsbooks.espn_auth import (
    TOKEN_CACHE_FILENAME,
    _random_id,
    ensure_install_id,
    load_token_cache,
    save_token_cache,
    token_cache_path,
)

# ---------------------------------------------------------------------------
# _random_id
# ---------------------------------------------------------------------------


def test_random_id_correct_length() -> None:
    rid = _random_id(23)
    assert len(rid) == 23


def test_random_id_uses_lowercase_alphanumeric() -> None:
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789")
    rid = _random_id(50)
    assert set(rid).issubset(allowed)


def test_random_id_varies() -> None:
    assert _random_id() != _random_id()


# ---------------------------------------------------------------------------
# token_cache_path
# ---------------------------------------------------------------------------


def test_token_cache_path_uses_correct_filename(tmp_path) -> None:
    path = token_cache_path(tmp_path)
    assert path.name == TOKEN_CACHE_FILENAME
    assert path.parent == tmp_path


# ---------------------------------------------------------------------------
# load_token_cache
# ---------------------------------------------------------------------------


def test_load_token_cache_returns_none_when_missing(tmp_path) -> None:
    assert load_token_cache(tmp_path) is None


def test_load_token_cache_returns_dict_when_valid(tmp_path) -> None:
    payload = {"install_id": "abc123", "anonymous_token": "tok"}
    (tmp_path / TOKEN_CACHE_FILENAME).write_text(json.dumps(payload), encoding="utf-8")
    result = load_token_cache(tmp_path)
    assert result == payload


def test_load_token_cache_returns_none_on_corrupt_json(tmp_path) -> None:
    (tmp_path / TOKEN_CACHE_FILENAME).write_text("not-json", encoding="utf-8")
    assert load_token_cache(tmp_path) is None


def test_load_token_cache_returns_none_when_file_is_list(tmp_path) -> None:
    (tmp_path / TOKEN_CACHE_FILENAME).write_text("[1, 2, 3]", encoding="utf-8")
    assert load_token_cache(tmp_path) is None


# ---------------------------------------------------------------------------
# save_token_cache
# ---------------------------------------------------------------------------


def test_save_token_cache_persists_install_id_and_token(tmp_path) -> None:
    save_token_cache("myid", "mytoken", data_dir=tmp_path)
    data = json.loads((tmp_path / TOKEN_CACHE_FILENAME).read_text())
    assert data["install_id"] == "myid"
    assert data["anonymous_token"] == "mytoken"


def test_save_token_cache_omits_token_when_none(tmp_path) -> None:
    save_token_cache("myid", None, data_dir=tmp_path)
    data = json.loads((tmp_path / TOKEN_CACHE_FILENAME).read_text())
    assert data["install_id"] == "myid"
    assert "anonymous_token" not in data


def test_save_token_cache_creates_parent_dir(tmp_path) -> None:
    nested = tmp_path / "nested" / "dir"
    save_token_cache("id1", "tok1", data_dir=nested)
    assert (nested / TOKEN_CACHE_FILENAME).exists()


# ---------------------------------------------------------------------------
# ensure_install_id
# ---------------------------------------------------------------------------


def test_ensure_install_id_generates_and_persists_on_first_use(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("ESPN_INSTALL_ID", raising=False)
    install_id = ensure_install_id(tmp_path)
    assert isinstance(install_id, str)
    assert len(install_id) == 23
    cached = load_token_cache(tmp_path)
    assert cached is not None
    assert cached["install_id"] == install_id


def test_ensure_install_id_reuses_cached_id(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("ESPN_INSTALL_ID", raising=False)
    first = ensure_install_id(tmp_path)
    second = ensure_install_id(tmp_path)
    assert first == second


def test_ensure_install_id_prefers_env_var(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ESPN_INSTALL_ID", "env-override-id")
    result = ensure_install_id(tmp_path)
    assert result == "env-override-id"
