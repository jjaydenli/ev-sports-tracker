"""Board API contract: push auth, envelope validation, and which run the page sees.

Oracle: the API contract and Decisions 4 and 9 in the live-web-board design, not the
store's implementation. Every test goes through FastAPI's ``TestClient`` against
``InMemoryBoardStore``; the Postgres store's SQL is checked manually against Neon.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from web.app import create_app
from web.store import InMemoryBoardStore

PUSH_TOKEN = "s3cret-push-token"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("BOARD_PUSH_TOKEN", PUSH_TOKEN)
    with TestClient(create_app(store=InMemoryBoardStore())) as test_client:
        yield test_client


def _auth(token: str = PUSH_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _coverage(run_id: str, sources: dict[str, dict]) -> dict:
    return {"run_id": run_id, "generated_at": "2026-11-08T22:30:00+00:00", "sources": sources}


def _run(
    run_id: str,
    *,
    generated_at: str,
    outcome: str,
    exit_code: int = 0,
    props: list[dict] | None = None,
    sources: dict[str, dict] | None = None,
) -> dict:
    payload: dict = {
        "run_id": run_id,
        "generated_at": generated_at,
        "exit_code": exit_code,
        "outcome": outcome,
        "coverage": _coverage(run_id, sources or {}),
    }
    if props is not None:
        payload["board"] = {"run_id": run_id, "props": props}
    return payload


def _nothing_stored(client: TestClient) -> bool:
    body = client.get("/api/board").json()
    return body["board"] is None and body["latest_run"] is None


def test_empty_store_returns_nulls(client: TestClient) -> None:
    response = client.get("/api/board")
    assert response.status_code == 200
    assert _nothing_stored(client)


def test_team_names_resolve_a_code_per_league(client: TestClient) -> None:
    """Oracle: the real teams. PHI is a different team in each league, and the
    Clippers go by two names; the page needs every spelling to match a search."""
    names = client.get("/api/board").json()["team_names"]
    assert names["NBA"]["PHI"] == ["Philadelphia 76ers"]
    assert names["MLB"]["PHI"] == ["Philadelphia Phillies"]
    assert sorted(names["NBA"]["LAC"]) == ["LA Clippers", "Los Angeles Clippers"]
    assert names["WNBA"]["PHX"] == ["Phoenix Mercury"]


def test_failed_run_does_not_displace_last_good_board(
    client: TestClient, s1_ev_rows: list[dict]
) -> None:
    good = _run("run-a", generated_at="2026-11-08T17:00:00+00:00", outcome="ok", props=s1_ev_rows)
    failed = _run(
        "run-b",
        generated_at="2026-11-08T20:00:00+00:00",
        outcome="failed",
        exit_code=1,
        sources={"betr:NBA": {"status": "failed", "reason": "auth", "prop_count": 0}},
    )
    assert client.post("/api/runs", json=good, headers=_auth()).status_code == 200
    assert client.post("/api/runs", json=failed, headers=_auth()).status_code == 200

    body = client.get("/api/board").json()
    assert body["board"]["run_id"] == "run-a"
    assert body["board"]["props"] == s1_ev_rows
    assert body["latest_run"]["run_id"] == "run-b"
    assert body["latest_run"]["outcome"] == "failed"
    assert body["latest_run"]["exit_code"] == 1
    assert body["latest_run"]["sources"]["betr:NBA"]["reason"] == "auth"


def test_newest_is_by_scrape_time_not_post_order(
    client: TestClient, s1_ev_rows: list[dict]
) -> None:
    """A publisher retry of an older run must not become the board the page shows."""
    newer = _run("run-new", generated_at="2026-11-08T20:00:00+00:00", outcome="ok", props=s1_ev_rows)
    older = _run(
        "run-old", generated_at="2026-11-08T17:00:00+00:00", outcome="ok", props=s1_ev_rows[:1]
    )
    client.post("/api/runs", json=newer, headers=_auth())
    client.post("/api/runs", json=older, headers=_auth())

    body = client.get("/api/board").json()
    assert body["board"]["run_id"] == "run-new"
    assert body["latest_run"]["run_id"] == "run-new"


def test_repeat_post_upserts_by_run_id(client: TestClient, s1_ev_rows: list[dict]) -> None:
    first = _run("run-a", generated_at="2026-11-08T17:00:00+00:00", outcome="failed", exit_code=1)
    retry = _run("run-a", generated_at="2026-11-08T17:00:00+00:00", outcome="ok", props=s1_ev_rows)
    client.post("/api/runs", json=first, headers=_auth())
    response = client.post("/api/runs", json=retry, headers=_auth())

    assert response.json() == {"run_id": "run-a", "outcome": "ok"}
    body = client.get("/api/board").json()
    assert body["latest_run"]["outcome"] == "ok"
    assert body["board"]["run_id"] == "run-a"


def test_sources_carry_dk_block_counts(client: TestClient, s1_ev_rows: list[dict]) -> None:
    sources = {
        "dk:NBA": {
            "status": "ok",
            "reason": None,
            "prop_count": 70,
            "requests": 40,
            "blocked_requests": 3,
            "error": "internal detail the page never shows",
        },
        "fd:NBA": {"status": "ok", "prop_count": 236},
    }
    run = _run(
        "run-a",
        generated_at="2026-11-08T17:00:00+00:00",
        outcome="ok",
        props=s1_ev_rows,
        sources=sources,
    )
    client.post("/api/runs", json=run, headers=_auth())

    got = client.get("/api/board").json()["latest_run"]["sources"]
    assert got["dk:NBA"] == {
        "status": "ok",
        "reason": None,
        "prop_count": 70,
        "requests": 40,
        "blocked_requests": 3,
    }
    assert got["fd:NBA"]["requests"] is None


def test_board_is_whole_by_default_and_limit_keeps_rank_order(
    client: TestClient, s1_ev_rows: list[dict]
) -> None:
    rows = [dict(s1_ev_rows[0], player=f"Player {i}") for i in range(250)]
    client.post(
        "/api/runs",
        json=_run("run-a", generated_at="2026-11-08T17:00:00+00:00", outcome="ok", props=rows),
        headers=_auth(),
    )

    assert client.get("/api/board").json()["board"]["props"] == rows
    assert client.get("/api/board?limit=2").json()["board"]["props"] == rows[:2]
    assert client.get("/api/board?limit=0").status_code == 422


@pytest.mark.parametrize(
    "headers",
    [
        {},
        _auth("wrong-token"),
        _auth(PUSH_TOKEN[:-1]),
        _auth(PUSH_TOKEN + "x"),
        {"Authorization": PUSH_TOKEN},
    ],
    ids=["no-header", "wrong", "prefix-of-token", "token-plus-suffix", "no-bearer-scheme"],
)
def test_push_rejects_bad_token(
    client: TestClient, s1_ev_rows: list[dict], headers: dict[str, str]
) -> None:
    run = _run("run-a", generated_at="2026-11-08T17:00:00+00:00", outcome="ok", props=s1_ev_rows)
    assert client.post("/api/runs", json=run, headers=headers).status_code == 401
    assert _nothing_stored(client)


def test_push_without_server_token_is_503(
    monkeypatch: pytest.MonkeyPatch, s1_ev_rows: list[dict]
) -> None:
    monkeypatch.delenv("BOARD_PUSH_TOKEN", raising=False)
    run = _run("run-a", generated_at="2026-11-08T17:00:00+00:00", outcome="ok", props=s1_ev_rows)
    with TestClient(create_app(store=InMemoryBoardStore())) as client:
        assert client.post("/api/runs", json=run, headers=_auth()).status_code == 503
        assert _nothing_stored(client)


def _mismatched_board(rows: list[dict]) -> dict:
    run = _run("run-a", generated_at="2026-11-08T17:00:00+00:00", outcome="ok", props=rows)
    run["board"]["run_id"] = "run-previous"
    return run


def _board_on_failed_run(rows: list[dict]) -> dict:
    run = _run("run-a", generated_at="2026-11-08T17:00:00+00:00", outcome="ok", props=rows)
    run["outcome"] = "failed"
    return run


def _ok_without_board(rows: list[dict]) -> dict:
    return _run("run-a", generated_at="2026-11-08T17:00:00+00:00", outcome="ok")


@pytest.mark.parametrize(
    "build",
    [_mismatched_board, _board_on_failed_run, _ok_without_board],
    ids=["board-run-id-mismatch", "board-on-failed-run", "ok-without-board"],
)
def test_push_rejects_inconsistent_envelope(
    client: TestClient, s1_ev_rows: list[dict], build
) -> None:
    assert client.post("/api/runs", json=build(s1_ev_rows), headers=_auth()).status_code == 422
    assert _nothing_stored(client)


def test_healthz(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
