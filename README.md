# EV Sports Tracker

Python pipeline that identifies +EV (positive expected value) player prop bets by comparing fixed-payout DFS lines against sharp sportsbook prices. Scrapes, normalizes, and de-vigs data from three sportsbooks with undocumented APIs — DraftKings, FanDuel, and ESPN BET (TheScore Bet) — then ranks opportunities by edge.

## Technical highlights

- **API reverse engineering** — all three sportsbooks have unpublished APIs. ESPN BET uses GET-based GraphQL persisted queries with an encrypted JWE bearer token (minted anonymously via a `Startup` op; cached and reactively re-minted on 401). DraftKings and FanDuel use undocumented REST endpoints discovered through DevTools captures.

- **De-vig algorithm for one-sided markets** — sportsbooks offer milestone props (`N+` over-only) with no paired under, making standard two-sided de-vigging impossible. When a contiguous `N+` ladder exists, the engine renormalizes the vig-inflated survival curve `S(N) = P(X≥N)` back to fair probability mass. Falls back to hold-shrink when only a lone threshold is available.

- **Match-context resolution** — props across books are matched on a canonical key `player|market|league|game|event_hour|live` where `event_hour` is the UTC hour-floor of game start. This eliminates cross-day ladder drift (e.g. a player listed for tomorrow's game being priced against today's Betr prop) and disambiguates MLB doubleheaders without special-case logic.

- **Data-driven book registry** — a `SharpBookConfig` dataclass drives all resolution logic (O/U interpolation strategy, milestone fallback, hold estimation). Adding a fourth sportsbook requires one registry entry; zero edits to resolution or assembly code.

## How it works

```
Betr (DFS)  ──┐
DraftKings  ──┤──▶  normalize  ──▶  match-context filter  ──▶  per-book resolve  ──▶  ranked +EV output
FanDuel     ──┤                         (canonical key)          (de-vig + ladder)
ESPN BET    ──┘
```

Each run scrapes all configured sources in parallel, normalizes to a shared `NormalizedProp` schema, then for each Betr prop filters the sharp pool to the same game snapshot before building O/U or milestone ladders. Multi-book consensus runs when two or more books price the same line exactly.

Architecture decisions: [`docs/design/`](docs/design/)

## Repository layout

```
ev-sports-tracker/
├── ev                            # bash entry point → backend/core/pipeline_runner.py
└── backend/
    ├── config/
    │   ├── api_headers.py        # Platform-specific headers and auth builders
    │   ├── market_maps.py        # Canonical market name translations
    │   ├── sharp_books.py        # SharpBookConfig registry (DK / FD / ESPN)
    │   ├── dk_subcategories.py   # DK subCategoryId map per market/league
    │   ├── team_abbrev.py        # Cross-book team abbreviation canonicalization
    │   ├── pipeline_sources.py   # League + source registry
    │   ├── espn_queries.py       # ESPN GraphQL persisted-query hashes
    │   └── settings.py           # Credential loading from .env
    ├── scrapers/
    │   ├── base_scraper.py       # Abstract base: authenticate → scrape → save
    │   ├── dfs/betr/             # Betr GraphQL (httpx)
    │   └── sportsbooks/
    │       ├── dk_engine.py / dk_api.py
    │       ├── fd_engine.py / fd_api.py
    │       └── espn_engine.py / espn_api.py / espn_auth.py
    ├── parsers/
    │   ├── betr_parser.py, dk_parser.py, fd_parser.py, espn_parser.py
    │   └── normalize.py          # Unified NormalizedProp output schema
    ├── core/
    │   ├── ladder_index.py       # Match-context keys, O/U + milestone ladder builders
    │   ├── resolution_math.py    # De-vig, logit interpolation, survival-curve normalization
    │   ├── line_adjustment.py    # Single-book resolution (BookQuote, ResolvedSharpQuote)
    │   ├── multi_book_resolver.py# Multi-book assembly and weighted consensus
    │   ├── engine.py             # EV calculation, per-prop sharp filtering
    │   ├── ev_pipeline.py        # Unified board → ranked JSON output
    │   └── pipeline_runner.py    # Orchestrator and CLI
    ├── tests/
    │   ├── fixtures/             # Captured API payloads (offline; no live network in tests)
    │   └── unit/
    └── data/processed/           # Run output (gitignored)
```

## Setup

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config/.env.example config/.env   # fill in credentials — never commit this file
```

**Betr auth:** set `BETR_REFRESH_TOKEN` + `BETR_KEYCLOAK_TOKEN_URL` (from DevTools on login). Probe: `python -m scrapers.dfs.betr.betr_auth --try-grant`. See [`docs/betting_odds/betr.md`](docs/betting_odds/betr.md).

```bash
pytest -q   # 550+ tests, offline fixtures only
```

## Daily refresh

From the repo root (activates `backend/.venv` automatically):

```bash
./ev
```

Runs all configured leagues (NBA, MLB, WNBA): parallel scrape → normalize → EV scan. Output written to `backend/data/processed/`:

| File | Contents |
|------|----------|
| `ev_opportunities.json` | Ranked +EV plays (default top 15) |
| `ev_run_diff.json` | New / removed / improved vs previous run |
| `match_report.json` | Match rates by league and source |
| `scrape_coverage.json` | Per-source scrape status |
| `unmatched_betr.json` | Betr lines with no sharp match |

**Useful flags:**

```bash
./ev --mlb                      # MLB only
./ev --books dk,espn            # subset of sharp books
./ev --top-n 25 --min-ev 0.02   # show top 25, mark edge > 2% as +EV
./ev --scrape-only              # scrape + normalize, skip EV
./ev --timing                   # wall-clock summary per pipeline stage
```

Platform-specific API notes: [`docs/betting_odds/`](docs/betting_odds/)

## Security

All API keys and tokens are loaded via `os.getenv()` from `config/.env`. No credentials are hardcoded or committed. The git history is scanned on pre-commit to block accidental `.env` inclusion.
