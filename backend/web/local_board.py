"""The local board: the board API served from this machine.

The cloud app's routes over :class:`~web.store.FileBoardStore`, plus a run trigger for the
page's refresh button. Started by ``npm run dev`` at the repo root
(``scripts/local-board.sh``), from ``backend``::

    uvicorn web.local_board:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from fastapi import FastAPI, HTTPException

from core.pipeline_artifacts import pipeline_run_in_progress
from core.pipeline_runner import DEFAULT_DATA_DIR
from web.app import create_app
from web.store import FileBoardStore

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND_DIR.parent
RUN_ARGS = ["--top-n", "all"]
RUN_LOG_FILENAME = "local_run.log"


class ChildProcess(Protocol):
    def poll(self) -> int | None: ...


Spawn = Callable[[list[str]], ChildProcess]


def _spawn_ev(args: list[str], *, log_path: Path) -> ChildProcess:
    """Start ``./ev`` detached from the server, output appended to ``log_path``."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as log:
        return subprocess.Popen(
            [str(_REPO_ROOT / "ev"), *args],
            cwd=_REPO_ROOT,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )


def create_local_app(data_dir: Path, *, spawn: Spawn | None = None) -> FastAPI:
    """The board API over ``data_dir``, plus ``GET|POST /api/local/run``."""
    data_dir = Path(data_dir)
    log_path = data_dir / RUN_LOG_FILENAME
    start: Spawn = spawn or (lambda args: _spawn_ev(args, log_path=log_path))
    app = create_app(store=FileBoardStore(data_dir))
    guard = threading.Lock()
    child: ChildProcess | None = None  # the child this app last spawned

    def running() -> bool:
        """The lock is held, or our child has not exited yet: it takes a few seconds to
        import and take the lock, and a second click in that window must not queue a
        second scrape."""
        child_alive = child is not None and child.poll() is None
        return child_alive or pipeline_run_in_progress(data_dir)

    @app.get("/api/local/run")
    def get_local_run() -> dict[str, bool]:
        return {"running": running()}

    @app.post("/api/local/run", status_code=202)
    def post_local_run() -> dict[str, bool]:
        nonlocal child
        with guard:
            if running():
                raise HTTPException(status_code=409, detail="a run is already going")
            child = start(list(RUN_ARGS))
        return {"running": True}

    return app


app = create_local_app(_BACKEND_DIR / DEFAULT_DATA_DIR)
