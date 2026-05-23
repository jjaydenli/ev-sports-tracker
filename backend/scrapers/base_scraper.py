"""Abstract base class enforcing the standard scraper pipeline."""

import json
import os
from abc import ABC, abstractmethod


class BaseScraper(ABC):
    sportsbook_name: str = "unknown"

    @abstractmethod
    async def authenticate(self) -> str | None:
        """Return a session token when authentication is required."""

    @abstractmethod
    async def scrape(self) -> list[dict]:
        """Fetch and normalize props for the current slate."""

    async def save(self, props: list[dict], output_path: str) -> None:
        """Persist normalized props to disk."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as file:
            json.dump(props, file, indent=4)

    async def run(self, output_path: str) -> list[dict]:
        """Execute the full scrape pipeline and persist results."""
        props = await self.scrape()
        await self.save(props, output_path)
        return props
