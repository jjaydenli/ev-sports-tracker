"""The local board reads ``data/processed``.

Oracle: the rows and ``run_id``s each test writes with the pipeline's own
``write_scrape_coverage``/``save_wrapped_board`` (via the ``test_web_publish`` helpers),
the lock the test itself holds, and the local board's rules: serve the disk, keep the
last good board while a run holds the lock, and start at most one run at a time. Every test goes
through FastAPI's ``TestClient``; spawning ``./ev`` is the one mocked process boundary.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.pipeline_artifacts import (
    EV_OUTPUT_FILENAME,
    SCRAPE_COVERAGE_FILENAME,
    pipeline_run_in_progress,
    pipeline_run_lock,
)
from tests.unit.test_web_publish import (
    _AUTH_FAILURE,
    _HEALTHY_SOURCES,
    _write_board,
    _write_coverage,
)
from web.local_board import create_local_app
from web.store import FileBoardStore


@dataclass
class _FakeChild:
    exit_code: int | None  # ``None``: still running, as ``Popen.poll()`` reports it

    def poll(self) -> int | None:
        return self.exit_code


@dataclass
class _FakeSpawn:
    child_exit_code: int | None = 0
    calls: list[list[str]] = field(default_factory=list)

    def __call__(self, args: list[str]) -> _FakeChild:
        self.calls.append(args)
        return _FakeChild(self.child_exit_code)


@pytest.fixture
def spawn() -> _FakeSpawn:
    return _FakeSpawn()


@pytest.fixture
def board_client(tmp_path: Path, spawn: _FakeSpawn) -> Iterator[TestClient]:
    with TestClient(create_local_app(tmp_path, spawn=spawn)) as client:
        yield client


def _running(client: TestClient) -> bool:
    response = client.get("/api/local/run")
    assert response.status_code == 200
    running: bool = response.json()["running"]
    return running


def _write_ok_run(data_dir: Path, run_id: str, rows: list[dict]) -> None:
    _write_coverage(data_dir, run_id, _HEALTHY_SOURCES)
    _write_board(data_dir, run_id, rows)


def test_lock_probe_sees_a_held_lock_and_a_free_one(tmp_path: Path) -> None:
    assert pipeline_run_in_progress(tmp_path) is False
    with pipeline_run_lock(tmp_path):
        assert pipeline_run_in_progress(tmp_path) is True
    assert pipeline_run_in_progress(tmp_path) is False


def test_fresh_machine_has_no_board_and_no_run(board_client: TestClient) -> None:
    body = board_client.get("/api/board").json()
    assert body["board"] is None
    assert body["latest_run"] is None


def test_board_follows_the_disk(
    tmp_path: Path, board_client: TestClient, s1_ev_rows: list[dict]
) -> None:
    _write_ok_run(tmp_path, "run-1", s1_ev_rows)
    body = board_client.get("/api/board").json()
    assert body["board"]["run_id"] == "run-1"
    assert body["board"]["props"] == s1_ev_rows
    assert body["latest_run"]["outcome"] == "ok"

    # A later run on disk replaces it without a restart.
    _write_ok_run(tmp_path, "run-2", s1_ev_rows[:1])
    body = board_client.get("/api/board").json()
    assert body["board"]["run_id"] == "run-2"
    assert body["board"]["props"] == s1_ev_rows[:1]


def test_clean_empty_run_reports_empty_without_a_board(
    tmp_path: Path, board_client: TestClient
) -> None:
    _write_ok_run(tmp_path, "run-1", [])
    body = board_client.get("/api/board").json()
    assert body["board"] is None
    assert body["latest_run"]["outcome"] == "empty"


def test_last_good_board_survives_a_failed_run(
    tmp_path: Path, board_client: TestClient, s1_ev_rows: list[dict]
) -> None:
    _write_ok_run(tmp_path, "run-a", s1_ev_rows)
    board_client.get("/api/board")
    # Betr auth failure: fresh coverage, the board file left at the prior run_id.
    _write_coverage(tmp_path, "run-b", _AUTH_FAILURE)
    body = board_client.get("/api/board").json()
    assert body["board"]["run_id"] == "run-a"
    assert body["board"]["props"] == s1_ev_rows
    assert body["latest_run"]["run_id"] == "run-b"
    assert body["latest_run"]["outcome"] == "failed"


def test_mid_run_serves_the_last_board_and_run_from_memory(
    tmp_path: Path, board_client: TestClient, s1_ev_rows: list[dict]
) -> None:
    _write_ok_run(tmp_path, "run-1", s1_ev_rows)
    board_client.get("/api/board")
    (tmp_path / EV_OUTPUT_FILENAME).unlink()
    (tmp_path / SCRAPE_COVERAGE_FILENAME).unlink()
    with pipeline_run_lock(tmp_path):
        body = board_client.get("/api/board").json()
        assert _running(board_client) is True
    assert body["board"]["run_id"] == "run-1"
    assert body["board"]["props"] == s1_ev_rows
    assert body["latest_run"]["run_id"] == "run-1"
    assert body["latest_run"]["outcome"] == "ok"


def test_upsert_is_refused(tmp_path: Path) -> None:
    """Nothing posts to the local board; a stray push must not silently vanish."""
    with pytest.raises(NotImplementedError):
        FileBoardStore(tmp_path).upsert_run(None)  # type: ignore[arg-type]


def test_run_button_starts_one_full_board_run(
    board_client: TestClient, spawn: _FakeSpawn
) -> None:
    assert _running(board_client) is False
    response = board_client.post("/api/local/run")
    assert response.status_code == 202
    assert response.json() == {"running": True}
    assert spawn.calls == [["--top-n", "all"]]
    # The fake child has already exited and no lock is held: idle again.
    assert _running(board_client) is False


def test_run_button_refused_while_a_terminal_run_holds_the_lock(
    tmp_path: Path, board_client: TestClient, spawn: _FakeSpawn
) -> None:
    with pipeline_run_lock(tmp_path):
        response = board_client.post("/api/local/run")
    assert response.status_code == 409
    assert spawn.calls == []


def test_run_button_refused_while_its_child_starts_up(
    board_client: TestClient, spawn: _FakeSpawn
) -> None:
    """The child takes a few seconds to import and take the lock; a lock-only check
    would report idle in that window and let a second click queue a second scrape."""
    spawn.child_exit_code = None
    assert board_client.post("/api/local/run").status_code == 202
    assert _running(board_client) is True
    assert board_client.post("/api/local/run").status_code == 409
    assert spawn.calls == [["--top-n", "all"]]
