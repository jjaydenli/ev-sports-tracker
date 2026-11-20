"""Run storage for the board API: one ``board_runs`` table, rows kept as opaque JSON."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from core.pipeline_artifacts import (
    EV_OUTPUT_FILENAME,
    LAST_GOOD_BOARD_DIRNAME,
    SCRAPE_COVERAGE_FILENAME,
    pipeline_run_in_progress,
)
from web.models import RunOutcome
from web.publish import build_run_payload


@dataclass(frozen=True)
class StoredRun:
    run_id: str
    generated_at: datetime
    received_at: datetime
    exit_code: int
    outcome: RunOutcome
    coverage: dict[str, Any]
    props: list[dict[str, Any]] | None


class BoardStore(Protocol):
    def setup(self) -> None: ...

    def upsert_run(self, run: StoredRun) -> None: ...

    def latest_run(self) -> StoredRun | None:
        """Newest run of any outcome, by scrape time."""
        ...

    def latest_board(self) -> StoredRun | None:
        """Newest ``ok`` run, by scrape time."""
        ...


def _newest(runs: list[StoredRun]) -> StoredRun | None:
    return max(runs, key=lambda run: (run.generated_at, run.run_id), default=None)


class InMemoryBoardStore:
    """Process-local store for tests and local development."""

    def __init__(self) -> None:
        self._runs: dict[str, StoredRun] = {}

    def setup(self) -> None:
        return None

    def upsert_run(self, run: StoredRun) -> None:
        self._runs[run.run_id] = run

    def latest_run(self) -> StoredRun | None:
        return _newest(list(self._runs.values()))

    def latest_board(self) -> StoredRun | None:
        return _newest([run for run in self._runs.values() if run.outcome == "ok"])


# --- Local board: the page's API over this checkout's data folder -------------------------


class FileBoardStore:
    """Reads the local ``data/processed`` on every call; nothing posts to it.

    Each read classifies the disk with ``build_run_payload`` (the publisher's own
    ok/empty/failed rule, read as exit 0) and remembers the newest run and newest ``ok``
    run it has seen. While a run holds the pipeline lock, its artifacts are wiped, so
    reads skip the disk and serve those memories: the same last good board the cloud
    keeps. A directory with no coverage file contributes no run.

    ``./ev`` wipes the disk before it scrapes, so a run stopped mid-scrape leaves no board.
    Each new ``ok`` run's two inputs are therefore copied into ``last_good_board/``, and a
    store with no board in memory (a restart) classifies that copy the same way.
    """

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = Path(data_dir)
        self._saved_dir = self._data_dir / LAST_GOOD_BOARD_DIRNAME
        self._last_run: StoredRun | None = None
        self._last_board: StoredRun | None = None

    def setup(self) -> None:
        return None

    def upsert_run(self, run: StoredRun) -> None:
        raise NotImplementedError("the local board reads the disk; nothing posts")

    @staticmethod
    def _read(data_dir: Path) -> StoredRun | None:
        payload = build_run_payload(data_dir, exit_code=0)
        if not payload["coverage"]:  # no coverage file: a ``nocoverage-*`` envelope
            return None
        board = payload["board"]
        return StoredRun(
            run_id=payload["run_id"],
            generated_at=datetime.fromisoformat(payload["generated_at"]),
            received_at=datetime.now(UTC),
            exit_code=payload["exit_code"],
            outcome=payload["outcome"],
            coverage=payload["coverage"],
            props=board["props"] if board is not None else None,
        )

    def _save(self) -> None:
        self._saved_dir.mkdir(exist_ok=True)
        for name in (SCRAPE_COVERAGE_FILENAME, EV_OUTPUT_FILENAME):
            shutil.copyfile(self._data_dir / name, self._saved_dir / name)

    def _refresh(self) -> None:
        if self._last_board is None:
            saved = self._read(self._saved_dir)
            if saved is not None and saved.outcome == "ok":
                self._last_board = saved
                self._last_run = self._last_run or saved
        if pipeline_run_in_progress(self._data_dir):
            return
        run = self._read(self._data_dir)
        if run is None:
            return
        self._last_run = run
        if run.outcome == "ok":
            if self._last_board is None or self._last_board.run_id != run.run_id:
                self._save()
            self._last_board = run

    def latest_run(self) -> StoredRun | None:
        self._refresh()
        return self._last_run

    def latest_board(self) -> StoredRun | None:
        self._refresh()
        return self._last_board


_COLUMNS = "run_id, generated_at, received_at, exit_code, outcome, coverage, props"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS board_runs (
    run_id text PRIMARY KEY,
    generated_at timestamptz NOT NULL,
    received_at timestamptz NOT NULL,
    exit_code integer NOT NULL,
    outcome text NOT NULL CHECK (outcome IN ('ok', 'empty', 'failed')),
    coverage jsonb NOT NULL,
    props jsonb,
    CHECK ((outcome = 'ok') = (props IS NOT NULL))
)
"""

_UPSERT = f"""
INSERT INTO board_runs ({_COLUMNS})
VALUES (%(run_id)s, %(generated_at)s, %(received_at)s, %(exit_code)s, %(outcome)s,
        %(coverage)s, %(props)s)
ON CONFLICT (run_id) DO UPDATE SET
    generated_at = EXCLUDED.generated_at,
    received_at = EXCLUDED.received_at,
    exit_code = EXCLUDED.exit_code,
    outcome = EXCLUDED.outcome,
    coverage = EXCLUDED.coverage,
    props = EXCLUDED.props
"""

_SELECT_NEWEST = (
    f"SELECT {_COLUMNS} FROM board_runs {{where}} "
    "ORDER BY generated_at DESC, run_id DESC LIMIT 1"
)


class PostgresBoardStore:
    """``board_runs`` in Postgres (Neon). One short connection per call.

    ``prepare_threshold=None`` keeps psycopg off server-side prepared statements,
    which a transaction-pooled connection string does not support.
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def _connect(self) -> psycopg.Connection[dict[str, Any]]:
        return psycopg.connect(self._dsn, prepare_threshold=None, row_factory=dict_row)

    def setup(self) -> None:
        with self._connect() as conn:
            conn.execute(_CREATE_TABLE)

    def upsert_run(self, run: StoredRun) -> None:
        params = {
            "run_id": run.run_id,
            "generated_at": run.generated_at,
            "received_at": run.received_at,
            "exit_code": run.exit_code,
            "outcome": run.outcome,
            "coverage": Jsonb(run.coverage),
            "props": Jsonb(run.props) if run.props is not None else None,
        }
        with self._connect() as conn:
            conn.execute(_UPSERT, params)

    def _select_newest(self, where: str) -> StoredRun | None:
        with self._connect() as conn:
            row = conn.execute(_SELECT_NEWEST.format(where=where)).fetchone()
        return StoredRun(**row) if row else None

    def latest_run(self) -> StoredRun | None:
        return self._select_newest("")

    def latest_board(self) -> StoredRun | None:
        return self._select_newest("WHERE outcome = 'ok'")
