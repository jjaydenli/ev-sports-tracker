"""Run storage for the board API: one ``board_runs`` table, rows kept as opaque JSON."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from web.models import RunOutcome


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
