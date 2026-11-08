"""Request and response models for the board API.

The envelope (run identity, outcome, coverage) is validated here. Board rows stay
opaque dicts: their schema belongs to ``core.engine``.
"""

from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import AwareDatetime, BaseModel, Field, model_validator

RunOutcome = Literal["ok", "empty", "failed"]


class BoardPayload(BaseModel):
    run_id: str = Field(min_length=1)
    props: list[dict[str, Any]]


class RunPayload(BaseModel):
    """One scrape job run, as posted by ``web.publish``."""

    run_id: str = Field(min_length=1)
    generated_at: AwareDatetime
    exit_code: int
    outcome: RunOutcome
    coverage: dict[str, Any]
    board: BoardPayload | None = None

    @model_validator(mode="after")
    def _board_belongs_to_ok_run(self) -> Self:
        if self.outcome == "ok" and self.board is None:
            raise ValueError("outcome 'ok' requires a board")
        if self.board is not None:
            if self.outcome != "ok":
                raise ValueError(f"a board was attached to a {self.outcome!r} run")
            if self.board.run_id != self.run_id:
                raise ValueError(
                    f"board run_id {self.board.run_id!r} does not match run {self.run_id!r}"
                )
        return self


class RunAccepted(BaseModel):
    run_id: str
    outcome: RunOutcome


class SourceHealth(BaseModel):
    """Public subset of one coverage entry (``error`` text is left out)."""

    status: str | None = None
    reason: str | None = None
    prop_count: int | None = None
    requests: int | None = None
    blocked_requests: int | None = None


class BoardView(BaseModel):
    run_id: str
    generated_at: AwareDatetime
    props: list[dict[str, Any]]


class LatestRunView(BaseModel):
    run_id: str
    generated_at: AwareDatetime
    outcome: RunOutcome
    exit_code: int
    sources: dict[str, SourceHealth]


class BoardResponse(BaseModel):
    board: BoardView | None
    latest_run: LatestRunView | None
