# EV Sports Tracker

Multi-platform Expected Value (+EV) sports betting engine. Compares fixed-payout player props on DFS apps (primarily **Betr**) against dynamically priced sharp sportsbook lines (**DraftKings**, **FanDuel**, **ESPN / TheScore Bet**) to find profitable discrepancies.

## Repository layout

```
ev-sports-tracker/
├── ev                            # bash wrapper → backend pipeline_runner
└── backend/
    ├── config/
    │   ├── api_headers.py        # Platform-specific user-agents/headers
    │   ├── market_maps.py        # Canonical market translations
    │   ├── dk_subcategories.py   # DK subCategoryId map
    │   ├── fd_competitions.py    # FD league/event discovery
    │   ├── fd_markets.py         # FD tab ↔ canonical market map
    │   ├── espn_competitions.py  # ESPN league/event discovery
    │   ├── espn_markets.py       # ESPN O/U drawer ↔ canonical market
    │   ├── espn_queries.py       # ESPN GraphQL persisted-query hashes
    │   ├── team_abbrev.py        # Cross-book team-abbrev canonicalization
    │   ├── pipeline_sources.py   # Leagues + DFS/book source registry
    │   ├── settings.py           # Credential loading from .env
    │   └── .env.example          # Template for local secrets
    ├── scripts/
    │   ├── probe_dk_subcategories.py
    │   ├── probe_fd_events.py
    │   └── probe_espn_events.py
    ├── utils/
    │   ├── math_utils.py         # Multiplicative de-vigging, conversion formulas
    │   └── formatting.py         # Standardizers (names, leagues, teams)
    ├── scrapers/
    │   ├── base_scraper.py       # Abstract base class enforcing standard pipeline
    │   ├── dfs/
    │   │   ├── betr/             # Betr GraphQL (httpx)
    │   │   └── dabble_engine.py  # Legacy
    │   └── sportsbooks/
    │       ├── dk_engine.py      # DraftKings markets API (httpx)
    │       ├── dk_api.py
    │       ├── fd_engine.py      # FanDuel event-page props
    │       ├── fd_api.py
    │       ├── espn_engine.py    # ESPN / TheScore Bet GraphQL (persisted queries)
    │       ├── espn_api.py
    │       └── espn_auth.py      # Anonymous JWE mint + cache
    ├── parsers/
    │   ├── betr_parser.py, dk_parser.py, fd_parser.py, espn_parser.py, normalize.py
    ├── core/
    │   ├── models.py             # NormalizedProp schemas (platform agnostic)
    │   ├── engine.py             # EV calculations
    │   ├── line_adjustment.py    # DK/FD/ESPN ladders, multi-book consensus + milestone EV
    │   ├── ev_pipeline.py        # Unified board → EV output
    │   ├── ev_display.py         # Ranked plays CLI table
    │   ├── ev_run_diff.py        # Consecutive run diff vs prior top-N
    │   ├── pipeline_timing.py    # Wall-clock stage timer
    │   └── pipeline_runner.py    # Daily refresh orchestrator
    ├── tests/
    │   ├── conftest.py           # Shared fixtures and mock HTTP responses
    │   ├── fixtures/
    │   └── unit/                 # Offline pytest (no live network)
    ├── data/
    │   └── processed/            # Parsed/normalized output (gitignored)
    ├── requirements.txt
    └── pytest.ini
```


## Setup

1. Create and activate a virtual environment:

   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Configure credentials locally:

   ```bash
   cp config/.env.example config/.env
   # or: cp config/.env.example .env
   ```

   Fill in credentials in `config/.env` or `backend/.env`. Never commit this file or tokens.

   **Betr (recommended):** `BETR_REFRESH_TOKEN` + `BETR_KEYCLOAK_TOKEN_URL` + `BETR_KEYCLOAK_CLIENT_ID` (from DevTools). Probe: `python -m scrapers.dfs.betr.betr_auth --try-grant`. See [docs/betting_odds/betr.md](docs/betting_odds/betr.md).

4. Run tests:

   ```bash
   pytest
   ```

## Daily refresh

From the repo root (activates `backend/.venv` if present) or from `backend/` with `.venv` active:

```bash
./ev
# same as: cd backend && python -m core.pipeline_runner
```

This runs **all configured leagues** (NBA, MLB, WNBA): for each league, dfs + books scrape in parallel, merge in memory, normalize once, then EV scan. Writes:

- `data/processed/scrape_coverage.json` — per source/league status (`ok`, `no_events`, `skipped`, `failed`) and `run_id`
- `data/processed/ev_opportunities.json` — top matched plays by EV (default 15; wrapped with `run_id`)
- `data/processed/ev_opportunities.previous.json` — prior run’s top-N (rotated before overwrite)
- `data/processed/ev_run_diff.json` — new / removed / improved / fell vs previous top-N
- `data/processed/match_report.json` — matched/unmatched counts, `by_league`, and `betr_match_rate_pct`
- `data/processed/unmatched_betr.json` — Betr lines with no sharp match
- `data/processed/unmatched_dk.json` — DK lines with no Betr twin on the same key

Each run uses **fresh scrape data only** (no stale normalized boards). Use the match files to judge scrape coverage and cross-book alignment before trusting +EV rows. Useful flags:

- `--books dk,fd,espn` — scrape selected sportsbooks; **all dfs apps always refresh** on EV runs
- `--leagues nba,mlb` — subset of leagues (default: all)
- `--scrape-only` — scrape + normalize only (no EV); `--dfs betr` limits dfs when debugging
- `--skip-scrape` — normalize + EV from existing master boards on disk (explicit override)
- `--top-n 15` — max rows written (default 15)
- `--min-ev 0.01` — mark `plus_ev` when edge > 1%; also **filters** output to those rows (default `0` shows all edges in top-N)
- `--plus-ev-only` — filter to `ev > --min-ev` (use with `--min-ev 0` for strictly positive EV only)
- `--include-flat-lines` — include Betr integer lines (push-adjusted breakeven; off by default)
- `--timing` — wall-clock summary per pipeline stage (scrape, normalize, EV)

DK subcategories, alternate lines, and line alignment: [docs/betting_odds/draftkings.md](docs/betting_odds/draftkings.md). FanDuel tabs and multi-book consensus: [docs/betting_odds/fanduel.md](docs/betting_odds/fanduel.md). ESPN GraphQL transport, O/U and milestone (LIST) drawer shapes: [docs/betting_odds/espn.md](docs/betting_odds/espn.md).

Betr auth: refresh grant (`BETR_REFRESH_TOKEN` + `BETR_KEYCLOAK_TOKEN_URL`; optional `BETR_KEYCLOAK_CLIENT_ID` from DevTools), or manual `BETR_BEARER_TOKEN`, or password grant. Probe: `python -m scrapers.dfs.betr.betr_auth --try-grant`. See [docs/betting_odds/betr.md](docs/betting_odds/betr.md).

## Security

All API keys, passwords, and JWTs must stay in `.env` and be loaded via `os.getenv()`. Do not hardcode credentials or tokens in source files.
