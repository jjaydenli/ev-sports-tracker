"""Board API: the scrape job posts runs, the site reads the latest board.

Run on Render with ``uvicorn web.app:app --host 0.0.0.0 --port $PORT`` from ``backend``.
Env: ``DATABASE_URL`` (Postgres), ``BOARD_PUSH_TOKEN`` (shared with the scrape job).
"""

from __future__ import annotations

import hmac
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request

from config.team_abbrev import team_names_by_code
from web.models import (
    BoardResponse,
    BoardView,
    LatestRunView,
    RunAccepted,
    RunPayload,
    SourceHealth,
)
from web.store import BoardStore, PostgresBoardStore, StoredRun


def _require_push_token(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    expected = os.getenv("BOARD_PUSH_TOKEN")
    if not expected:
        raise HTTPException(status_code=503, detail="push token not configured")
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(
        token.encode(), expected.encode()
    ):
        raise HTTPException(status_code=401, detail="invalid push token")


def _store(request: Request) -> BoardStore:
    store: BoardStore = request.app.state.store
    return store


def _latest_run_view(run: StoredRun) -> LatestRunView:
    sources = run.coverage.get("sources") or {}
    return LatestRunView(
        run_id=run.run_id,
        generated_at=run.generated_at,
        outcome=run.outcome,
        exit_code=run.exit_code,
        sources={
            key: SourceHealth.model_validate(entry)
            for key, entry in sources.items()
            if isinstance(entry, dict)
        },
    )


def create_app(store: BoardStore | None = None) -> FastAPI:
    """Build the app; with no ``store``, startup connects to ``DATABASE_URL``."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved = store
        if resolved is None:
            dsn = os.getenv("DATABASE_URL")
            if not dsn:
                raise RuntimeError("DATABASE_URL is not set")
            resolved = PostgresBoardStore(dsn)
        resolved.setup()
        app.state.store = resolved
        yield

    app = FastAPI(title="EV board API", lifespan=lifespan)

    @app.post(
        "/api/runs",
        response_model=RunAccepted,
        dependencies=[Depends(_require_push_token)],
    )
    def post_run(
        payload: RunPayload, board_store: Annotated[BoardStore, Depends(_store)]
    ) -> RunAccepted:
        board_store.upsert_run(
            StoredRun(
                run_id=payload.run_id,
                generated_at=payload.generated_at,
                received_at=datetime.now(UTC),
                exit_code=payload.exit_code,
                outcome=payload.outcome,
                coverage=payload.coverage,
                props=payload.board.props if payload.board is not None else None,
            )
        )
        return RunAccepted(run_id=payload.run_id, outcome=payload.outcome)

    @app.get("/api/board", response_model=BoardResponse)
    def get_board(
        board_store: Annotated[BoardStore, Depends(_store)],
        limit: Annotated[int | None, Query(ge=1)] = None,
    ) -> BoardResponse:
        """Newest good board plus the latest run's health; no ``limit`` returns every row
        (the page paginates in the browser)."""
        board_run = board_store.latest_board()
        latest = board_store.latest_run()
        board = (
            BoardView(
                run_id=board_run.run_id,
                generated_at=board_run.generated_at,
                props=(board_run.props or [])[:limit],
            )
            if board_run is not None
            else None
        )
        return BoardResponse(
            board=board,
            latest_run=_latest_run_view(latest) if latest is not None else None,
            team_names=team_names_by_code(),
        )

    @app.get("/healthz")
    def healthz() -> dict[str, bool]:
        return {"ok": True}

    return app


app = create_app()
