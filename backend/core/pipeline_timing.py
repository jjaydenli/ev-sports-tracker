"""Wall-clock timing helpers for pipeline_runner."""

from __future__ import annotations

import time
from contextlib import AbstractContextManager
from dataclasses import dataclass, field

from loguru import logger


def format_elapsed(seconds: float) -> str:
    """Format a duration for log output."""
    if seconds < 0.001:
        return f"{seconds * 1_000_000:.0f}us"
    if seconds < 1.0:
        return f"{seconds * 1000:.0f}ms"
    return f"{seconds:.2f}s"


@dataclass
class PipelineTimer:
    """Collect labeled stage durations and print an aligned summary."""

    enabled: bool = True
    _records: list[tuple[str, float]] = field(default_factory=list)
    _started_at: float = field(default_factory=time.perf_counter)

    @classmethod
    def disabled(cls) -> PipelineTimer:
        return cls(enabled=False)

    def record(self, label: str, elapsed: float) -> None:
        if self.enabled:
            self._records.append((label, elapsed))

    def stage(self, label: str) -> AbstractContextManager[object]:
        if not self.enabled:
            return _NullStage()
        return _Stage(self, label)

    def total_elapsed(self) -> float:
        return time.perf_counter() - self._started_at

    def log_summary(self) -> None:
        if not self.enabled or not self._records:
            return
        width = max(len(label) for label, _ in self._records)
        logger.info("timing:")
        for label, elapsed in self._records:
            logger.info(f"  {label:<{width}}  {format_elapsed(elapsed)}")
        logger.info(f"  {'total':<{width}}  {format_elapsed(self.total_elapsed())}")


class _NullStage:
    def __enter__(self) -> object:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


class _Stage:
    def __init__(self, timer: PipelineTimer, label: str) -> None:
        self._timer = timer
        self._label = label
        self._started_at = 0.0

    def __enter__(self) -> _Stage:
        self._started_at = time.perf_counter()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._timer.record(self._label, time.perf_counter() - self._started_at)
