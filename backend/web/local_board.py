"""The local board: the board API served from this machine.

The cloud app's routes over :class:`~web.store.FileBoardStore`, plus the page's run
controls: Refresh (one ``./ev``), Auto-refresh (``./loop``), Stop (ends either) and Shut
down (ends any run, then both servers, as Ctrl-C does). Started by ``npm run dev`` at the
repo root (``scripts/local-board.sh``), from ``backend``::

    uvicorn web.local_board:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from fastapi import BackgroundTasks, FastAPI, HTTPException

from core.pipeline_artifacts import pipeline_run_in_progress
from core.pipeline_runner import DEFAULT_DATA_DIR
from web.app import create_app
from web.store import FileBoardStore

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND_DIR.parent
# How long a page-started auto-refresh runs. Passed to ./loop rather than left to its
# default, so the stop time the page shows is the one ./loop enforces. ./loop checks it
# between runs, so a run going at the deadline still finishes.
LOOP_SECONDS = 300
# What each run button starts, relative to the repo root. A loop brings ./loop's desktop
# toasts.
RUN_COMMANDS: dict[str, list[str]] = {
    "refresh": ["./ev", "--top-n", "all"],
    "loop": ["./loop", "--timeout", str(LOOP_SECONDS), "--top-n", "all"],
}
RUN_LOG_FILENAME = "local_run.log"
_STOP_GRACE_SECONDS = 5


class ChildProcess(Protocol):
    def poll(self) -> int | None: ...

    def stop(self) -> None: ...


Spawn = Callable[[list[str]], ChildProcess]


class _Child:
    """A started run in its own process group, so stopping it reaches ``./ev`` under
    ``./loop`` and nothing else."""

    def __init__(self, popen: subprocess.Popen[bytes]) -> None:
        self._popen = popen

    def poll(self) -> int | None:
        return self._popen.poll()

    def stop(self) -> None:
        if self._popen.poll() is not None:
            return
        try:
            os.killpg(self._popen.pid, signal.SIGTERM)
            self._popen.wait(timeout=_STOP_GRACE_SECONDS)
        except ProcessLookupError:
            return
        except subprocess.TimeoutExpired:
            os.killpg(self._popen.pid, signal.SIGKILL)
            self._popen.wait()


def _spawn(argv: list[str], *, log_path: Path) -> ChildProcess:
    """Start ``argv`` from the repo root, output appended to ``log_path``."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as log:
        return _Child(
            subprocess.Popen(
                [str(_REPO_ROOT / argv[0]), *argv[1:]],
                cwd=_REPO_ROOT,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        )


def _interrupt_own_group() -> None:
    """Ctrl-C from the page: SIGINT to this process group (``npm run dev``, the script,
    uvicorn, ``next dev``)."""
    os.killpg(os.getpgrp(), signal.SIGINT)


def create_local_app(
    data_dir: Path,
    *,
    spawn: Spawn | None = None,
    shutdown: Callable[[], None] = _interrupt_own_group,
) -> FastAPI:
    """The board API over ``data_dir``, plus the ``/api/local/*`` run controls."""
    data_dir = Path(data_dir)
    log_path = data_dir / RUN_LOG_FILENAME
    start: Spawn = spawn or (lambda argv: _spawn(argv, log_path=log_path))
    store = FileBoardStore(data_dir)
    app = create_app(store=store)
    guard = threading.Lock()
    child: ChildProcess | None = None  # the child this app last spawned
    child_kind: str | None = None
    loop_ends_at: datetime | None = None

    def child_alive() -> bool:
        return child is not None and child.poll() is None

    def running() -> bool:
        """The lock is held, or our child has not exited yet: it takes a few seconds to
        import and take the lock, and a second click in that window must not queue a
        second scrape."""
        return child_alive() or pipeline_run_in_progress(data_dir)

    def looping() -> bool:
        return child_kind == "loop" and child_alive()

    def begin(kind: str) -> dict[str, bool]:
        nonlocal child, child_kind, loop_ends_at
        with guard:
            if running():
                raise HTTPException(status_code=409, detail="a run is already going")
            started = datetime.now(UTC)
            child = start(list(RUN_COMMANDS[kind]))
            child_kind = kind
            loop_ends_at = started + timedelta(seconds=LOOP_SECONDS) if kind == "loop" else None
        return {"running": True}

    def end_child() -> None:
        with guard:
            if child_alive():
                assert child is not None
                child.stop()

    inner_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with inner_lifespan(app):
            try:
                yield
            finally:
                end_child()  # Ctrl-C: nothing the page started outlives the server

    app.router.lifespan_context = lifespan

    @app.get("/api/local/run")
    def get_local_run() -> dict[str, Any]:
        board = store.latest_board()
        return {
            "running": running(),
            "looping": looping(),
            "stoppable": child_alive(),
            "loop_ends_at": loop_ends_at.isoformat() if looping() and loop_ends_at else None,
            "board_run_id": board.run_id if board is not None else None,
        }

    @app.post("/api/local/run", status_code=202)
    def post_local_run() -> dict[str, bool]:
        return begin("refresh")

    @app.post("/api/local/loop", status_code=202)
    def post_local_loop() -> dict[str, bool]:
        return begin("loop")

    @app.post("/api/local/stop")
    def post_local_stop() -> dict[str, bool]:
        with guard:
            if not child_alive():
                raise HTTPException(status_code=409, detail="no page-started run is going")
            assert child is not None
            child.stop()
        return {"running": running()}

    @app.post("/api/local/shutdown", status_code=202)
    def post_local_shutdown(tasks: BackgroundTasks) -> dict[str, bool]:
        end_child()
        tasks.add_task(shutdown)  # after the response, so the page hears the 202
        return {"running": False}

    return app


app = create_local_app(_BACKEND_DIR / DEFAULT_DATA_DIR)
