"""The local board reads ``data/processed``.

Oracle: the rows and ``run_id``s each test writes with the pipeline's own
``write_scrape_coverage``/``save_wrapped_board`` (via the ``test_web_publish`` helpers),
the lock the test itself holds, and the local board's rules: serve the disk, keep the
last good board while a run holds the lock, and start at most one run at a time. Every test goes
through FastAPI's ``TestClient``. Spawning and stopping a run, and signalling the server's own
process group, are the mocked process boundaries.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.pipeline_artifacts import (
    EV_OUTPUT_FILENAME,
    LAST_GOOD_BOARD_DIRNAME,
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
from web.app import create_app
from web.local_board import create_local_app
from web.store import FileBoardStore, InMemoryBoardStore


@dataclass
class _FakeChild:
    exit_code: int | None  # ``None``: still running, as ``Popen.poll()`` reports it
    stopped: bool = False

    def poll(self) -> int | None:
        return self.exit_code

    def stop(self) -> None:
        self.stopped = True
        self.exit_code = -15


@dataclass
class _FakeSpawn:
    child_exit_code: int | None = 0
    calls: list[list[str]] = field(default_factory=list)
    children: list[_FakeChild] = field(default_factory=list)

    def __call__(self, argv: list[str]) -> _FakeChild:
        self.calls.append(argv)
        self.children.append(_FakeChild(self.child_exit_code))
        return self.children[-1]


@dataclass
class _FakeShutdown:
    calls: int = 0

    def __call__(self) -> None:
        self.calls += 1


# The commands Decisions 9 and 13 name, written out rather than read from the module.
_REFRESH = ["./ev", "--top-n", "all"]
_LOOP = ["./loop", "--top-n", "all"]
_ROUTE = {"refresh": "/api/local/run", "loop": "/api/local/loop"}


@pytest.fixture
def spawn() -> _FakeSpawn:
    return _FakeSpawn()


@pytest.fixture
def shutdown() -> _FakeShutdown:
    return _FakeShutdown()


@pytest.fixture
def board_client(
    tmp_path: Path, spawn: _FakeSpawn, shutdown: _FakeShutdown
) -> Iterator[TestClient]:
    app = create_local_app(tmp_path, spawn=spawn, shutdown=shutdown)
    with TestClient(app) as client:
        yield client


def _status(client: TestClient) -> dict:
    response = client.get("/api/local/run")
    assert response.status_code == 200
    body: dict = response.json()
    return body


def _running(client: TestClient) -> bool:
    running: bool = _status(client)["running"]
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


def _wipe(data_dir: Path) -> None:
    """What ``./ev`` does before it scrapes, so a run stopped mid-scrape leaves this."""
    (data_dir / EV_OUTPUT_FILENAME).unlink()
    (data_dir / SCRAPE_COVERAGE_FILENAME).unlink()


def test_restart_after_a_stopped_run_serves_the_last_good_board(
    tmp_path: Path, s1_ev_rows: list[dict]
) -> None:
    _write_ok_run(tmp_path, "run-1", s1_ev_rows)
    written_at = FileBoardStore(tmp_path).latest_board()
    assert written_at is not None
    _wipe(tmp_path)

    board = FileBoardStore(tmp_path).latest_board()  # a new process: nothing in memory
    assert board is not None
    assert board.run_id == "run-1"
    assert board.props == s1_ev_rows
    # The scrape's own time, read back from the coverage the test wrote, not the copy's.
    saved_coverage = tmp_path / LAST_GOOD_BOARD_DIRNAME / SCRAPE_COVERAGE_FILENAME
    coverage = json.loads(saved_coverage.read_text())
    assert board.generated_at == datetime.fromisoformat(coverage["generated_at"])
    assert board.generated_at == written_at.generated_at


def test_restart_mid_run_serves_the_last_good_board(
    tmp_path: Path, s1_ev_rows: list[dict]
) -> None:
    _write_ok_run(tmp_path, "run-1", s1_ev_rows)
    FileBoardStore(tmp_path).latest_board()
    _wipe(tmp_path)
    with pipeline_run_lock(tmp_path):
        board = FileBoardStore(tmp_path).latest_board()
    assert board is not None
    assert board.run_id == "run-1"


def test_a_failed_run_never_replaces_the_saved_board(
    tmp_path: Path, s1_ev_rows: list[dict]
) -> None:
    _write_ok_run(tmp_path, "run-a", s1_ev_rows)
    FileBoardStore(tmp_path).latest_board()
    # Betr auth failure: fresh coverage, the board file left at the prior run_id.
    _write_coverage(tmp_path, "run-b", _AUTH_FAILURE)
    FileBoardStore(tmp_path).latest_board()
    _wipe(tmp_path)

    board = FileBoardStore(tmp_path).latest_board()
    assert board is not None
    assert board.run_id == "run-a"
    assert board.props == s1_ev_rows


def test_a_newer_good_run_replaces_the_saved_board(
    tmp_path: Path, s1_ev_rows: list[dict]
) -> None:
    store = FileBoardStore(tmp_path)
    _write_ok_run(tmp_path, "run-1", s1_ev_rows)
    store.latest_board()
    _write_ok_run(tmp_path, "run-2", s1_ev_rows[:1])
    store.latest_board()
    _wipe(tmp_path)

    board = FileBoardStore(tmp_path).latest_board()
    assert board is not None
    assert board.run_id == "run-2"
    assert board.props == s1_ev_rows[:1]


def test_live_app_has_no_local_routes(tmp_path: Path) -> None:
    """Render runs ``web.app:app``; a run trigger there would let the cloud start scrapes."""

    def local_paths(app: FastAPI) -> set[str]:
        paths = {getattr(route, "path", "") for route in app.routes}
        return {path for path in paths if path.startswith("/api/local")}

    assert local_paths(create_local_app(tmp_path))  # the walk sees local routes where they exist
    assert local_paths(create_app(store=InMemoryBoardStore())) == set()


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
    assert spawn.calls == [_REFRESH]
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
    assert spawn.calls == [_REFRESH]


def test_loop_button_starts_one_loop(board_client: TestClient, spawn: _FakeSpawn) -> None:
    response = board_client.post("/api/local/loop")
    assert response.status_code == 202
    assert response.json() == {"running": True}
    assert spawn.calls == [_LOOP]


def test_loop_button_refused_while_a_terminal_run_holds_the_lock(
    tmp_path: Path, board_client: TestClient, spawn: _FakeSpawn
) -> None:
    with pipeline_run_lock(tmp_path):
        assert board_client.post("/api/local/loop").status_code == 409
    assert spawn.calls == []


@pytest.mark.parametrize(
    ("first", "second"),
    [("refresh", "loop"), ("loop", "refresh"), ("loop", "loop")],
)
def test_page_runs_never_overlap(
    board_client: TestClient, spawn: _FakeSpawn, first: str, second: str
) -> None:
    spawn.child_exit_code = None
    assert board_client.post(_ROUTE[first]).status_code == 202
    assert board_client.post(_ROUTE[second]).status_code == 409
    assert len(spawn.calls) == 1


def test_stop_ends_a_running_loop(board_client: TestClient, spawn: _FakeSpawn) -> None:
    spawn.child_exit_code = None
    board_client.post("/api/local/loop")
    assert _status(board_client)["looping"] is True

    response = board_client.post("/api/local/stop")
    assert response.status_code == 200
    assert spawn.children[0].stopped is True
    status = _status(board_client)
    assert status["running"] is False
    assert status["looping"] is False


def test_stop_refuses_a_refresh_run(board_client: TestClient, spawn: _FakeSpawn) -> None:
    """A single run ends in under 30 s and is not stoppable (Decision 16)."""
    spawn.child_exit_code = None
    board_client.post("/api/local/run")
    assert _status(board_client)["looping"] is False

    assert board_client.post("/api/local/stop").status_code == 409
    assert spawn.children[0].stopped is False
    assert _running(board_client) is True


def test_stop_refused_with_nothing_running(board_client: TestClient) -> None:
    assert board_client.post("/api/local/stop").status_code == 409


def test_status_names_the_board_on_disk(
    tmp_path: Path, board_client: TestClient, s1_ev_rows: list[dict]
) -> None:
    assert _status(board_client)["board_run_id"] is None
    _write_ok_run(tmp_path, "run-1", s1_ev_rows)
    assert _status(board_client)["board_run_id"] == "run-1"
    # A loop's next run lands: the page reloads on this change.
    _write_ok_run(tmp_path, "run-2", s1_ev_rows[:1])
    assert _status(board_client)["board_run_id"] == "run-2"


def test_server_shutdown_ends_a_page_started_run(
    tmp_path: Path, spawn: _FakeSpawn, shutdown: _FakeShutdown
) -> None:
    """Ctrl-C reaches uvicorn, whose shutdown ends the child (Decision 15)."""
    spawn.child_exit_code = None
    with TestClient(create_local_app(tmp_path, spawn=spawn, shutdown=shutdown)) as client:
        client.post("/api/local/loop")
        assert spawn.children[0].stopped is False
    assert spawn.children[0].stopped is True
    assert shutdown.calls == 0


def test_shut_down_button_ends_the_run_then_the_servers(
    board_client: TestClient, spawn: _FakeSpawn, shutdown: _FakeShutdown
) -> None:
    spawn.child_exit_code = None
    board_client.post("/api/local/run")
    response = board_client.post("/api/local/shutdown")
    assert response.status_code == 202
    assert spawn.children[0].stopped is True
    assert shutdown.calls == 1
