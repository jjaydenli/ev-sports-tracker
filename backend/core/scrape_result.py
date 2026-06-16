"""Scrape outcome types for pipeline coverage reporting."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

ScrapeStatus = Literal["ok", "no_events", "skipped", "failed"]


@dataclass
class ScrapeResult:
    """Outcome of one source × league scrape attempt."""

    source: str
    league: str
    status: ScrapeStatus
    prop_count: int = 0
    error: str | None = None
    reason: str | None = None
    props: list[dict] = field(default_factory=list)

    @property
    def coverage_key(self) -> str:
        return f"{self.source}:{self.league}"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("props", None)
        return payload
