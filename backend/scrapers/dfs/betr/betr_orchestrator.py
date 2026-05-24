"""Thin entrypoint for manual Betr slate runs."""

import asyncio

from scrapers.dfs.betr.betr_engine import main

if __name__ == "__main__":
    asyncio.run(main())
