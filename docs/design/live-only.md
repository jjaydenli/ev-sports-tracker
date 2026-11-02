# `--live-only` scrape mode

## Context

A full `./ev` run scrapes pregame and live props together, even when only in-progress games matter.
A live check has no use for the pregame half of that scrape.

## Design decisions

- **The flag filters the scrape, not the board.** `live_only` is a keyword-only argument passed from
  `run_refresh` through `scrape_source_league` to each league scraper. Downstream stages need no
  change: they receive fewer rows.
- **Each source filters at the cheapest point it has.** `DraftKingsEngine` and `ESPNEngine` skip
  pregame events before requesting any tab or drawer, using the live state they already resolve. Betr
  filters finished rows on `is_live` through `_only_live`.
- **FanDuel is skipped, not filtered.** FanDuel rows are never marked live, and a live Betr prop only
  matches a live row, so scraping it would spend time on rows that cannot match. It reports a
  `skipped` result with reason `no_live_support`.
- **`--skip-scrape` is rejected.** The flag has no effect without a scrape, and `main` exits with an
  error rather than ignoring it silently.

## Non-goals

- Live FanDuel support.

## Files / modules

| Path | Change |
|------|--------|
| `backend/core/pipeline_runner.py` | `--live-only` flag, `--skip-scrape` rejection, pass-through |
| `backend/core/pipeline_scrape.py` | per-source handling, `_only_live` |
| `backend/scrapers/sportsbooks/dk_engine.py`, `espn_engine.py` | `live_only` skips pregame events |

## Test plan

- DraftKings and ESPN request nothing for pregame events when `live_only` is set.
- `test_pipeline_scrape.py` covers row filtering and the FanDuel skip result.
- `main` rejects `--live-only` with `--skip-scrape`.
