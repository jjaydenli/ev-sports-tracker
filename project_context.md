# Master Project Context: Multi-Platform EV Betting Engine


**Last verified:** 2026-06-16 (agent workflow trim + proxyman scope; platform detail in docs/betting_odds/)

## 1. Project Overview

This project is a high-throughput Expected Value (+EV) sports betting engine. Its primary goal is to find profitable mathematical discrepancies by comparing fixed-payout player props on Daily Fantasy Sports (DFS) apps (primarily **Betr**) against dynamically priced sharp sportsbook lines (**DraftKings**, **FanDuel**).

The system standardizes disparate naming conventions across books, calculates no-vig fair value on the fly, and outputs opportunities in a standardized JSON format. **Dabble** integration is archived under `backend/archive/dabble/`; mobile-only Proxyman capture notes (not used for Betr/DK/FD) remain in `docs/proxyman_dabble_setup.md`.


## 2. Tech Stack & Libraries

* **Language:** Python (async-first with `asyncio`)
* **DFS ingestion:** `httpx` for async HTTP (Betr GraphQL)
* **Sportsbook ingestion:** `httpx` async HTTP for DraftKings league/event/market APIs (`dk_api.py`, `dk_engine.py`) and FanDuel league + event-page APIs (`fd_api.py`, `fd_engine.py`); headers via `api_headers.py` (`DK_*`, `FD_*`; no sportsbook bearer in `settings.py` today)
* **Data processing:** `json`, `re`; relational array joins for DFS payloads
* **Logging:** `loguru`
* **Testing:** `pytest`, `pytest-asyncio`, `pytest-mock` (offline fixtures only)
* *(Future: FastAPI, Redis, PostgreSQL, React)*

## 3. Platform-Specific Extraction Logic

Platform detail lives in [docs/betting_odds/](docs/betting_odds/). Summary below; each doc covers auth, scrape policy, markets, probes, and EV hooks.

### Betr (primary DFS)

* **Role:** Fixed-payout DFS props compared to sharp books.
* **Code:** `backend/scrapers/dfs/betr/`, `backend/parsers/betr_parser.py`
* **Detail:** [docs/betting_odds/betr.md](docs/betting_odds/betr.md) — GraphQL auth, wide fetch, `REGULAR` / `allowedOptions`, -120 breakeven.

### DraftKings (sharp sportsbook)

* **Role:** Sharp O/U ladders and milestone fallbacks; primary input to `line_adjustment.py`.
* **Code:** `dk_engine.py`, `dk_api.py`, `dk_parser.py`, `config/dk_subcategories.py`
* **Detail:** [docs/betting_odds/draftkings.md](docs/betting_odds/draftkings.md) — slates, subcategories, eligible `line_source` values.

### FanDuel (sharp sportsbook)

* **Role:** Second sharp book; multi-book consensus when DK+FD align at the Betr line.
* **Code:** `fd_api.py`, `fd_engine.py`, `fd_parser.py`, `config/fd_markets.py`, `scripts/probe_fd_events.py`
* **Detail:** [docs/betting_odds/fanduel.md](docs/betting_odds/fanduel.md) — event discovery, tabs, O/U vs milestones.

### Dabble (archived)

* **Code:** `backend/archive/dabble/` · **Detail:** [docs/betting_odds/dabble.md](docs/betting_odds/dabble.md) · mobile-only capture: [docs/proxyman_dabble_setup.md](docs/proxyman_dabble_setup.md)

### MLB

* **Detail:** [docs/betting_odds/mlb.md](docs/betting_odds/mlb.md) — league-specific market coverage and pipeline notes.

## 4. Quantitative Modeling & Math

* **Market mapping:** Platform names normalized via `PLATFORM_MARKET_MAPPINGS` → `MARKETS` in `config/market_maps.py`.
* **De-vigging:** DK American odds → implied probabilities; **multiplicative** vig removal in `utils/math_utils.py`.
* **EV calculation:** `find_ev_opportunities` / `compare_betr_vs_draftkings` in `core/engine.py` — resolve sharp quote per Betr line via `line_adjustment.py` (DK ladder, optional FD exact, optional `multi_book_consensus`), multiplicative de-vig on eligible O/U, one row per allowed Betr side, ranked by EV. Each row gets `plus_ev` when `ev > min_ev`. Optional `filter_min_ev` drops sub-threshold rows before `top_n` (pipeline: auto when `--min-ev > 0`, or `--plus-ev-only` with any `--min-ev`). `run_ev_scan` logs a ranked plays table (`core/ev_display.py`: Hit%, EV%, +EV, DK/FD O/U, `line_source` — compact widths) plus run-over-run diff (`core/ev_run_diff.py`: new / removed / improved / fell vs prior top-N). JSON output capped at `top_n` (default 15). Default DFS breakeven: `BETR_STANDARD_BREAKEVEN_ODDS` (-120); flat integer Betr lines optional (`--include-flat-lines`).

## 5. Architecture & File Structure

```text
ev-sports-tracker/
│   ├── rules/                  # path-scoped: backend/**, docs/plans/**
│   └── skills/design-handoff/  # plan-file workflow → docs/plans/
├── docs/
│   ├── plans/                  # _template.md, _example.md, feature handoffs
├── ev                            # bash wrapper → backend pipeline_runner (same flags)
└── backend/
    ├── config/
    │   ├── api_headers.py
    │   ├── market_maps.py
    │   ├── settings.py
    │   ├── dk_subcategories.py
    │   ├── dk_discovery.py     # wide-scan ID ranges; discovery output paths
    │   ├── discovery/          # per-league progress manifests (mlb.yaml)
    │   ├── fd_competitions.py
    │   ├── fd_markets.py       # tab ↔ canonical; FD_DEFAULT_SCRAPE_MARKETS; parse_player_ou_market_type
    │   ├── .env.example        # Betr Keycloak URL + betr-rn; FD_*; DK_MARKETS_MAX_CONCURRENT
    │   └── .env                # local secrets (gitignored)
    ├── scripts/
    │   ├── probe_dk_discover.py
    │   ├── probe_dk_subcategories.py
    │   └── probe_fd_events.py
    ├── utils/
    │   ├── math_utils.py
    │   └── formatting.py
    ├── scrapers/
    │   ├── base_scraper.py
    │   ├── dfs/
    │   │   ├── betr/           # betr_api, betr_auth, betr_engine, betr_orchestrator
    │   │   └── dabble_engine.py
    │   └── sportsbooks/
    │       ├── dk_engine.py
    │       ├── dk_api.py
    │       ├── fd_api.py       # league discovery; flatten; group_fd_line_rows
    │       └── fd_engine.py
    ├── parsers/
    │   ├── betr_parser.py
    │   ├── dk_parser.py
    │   ├── fd_parser.py
    │   └── normalize.py
    ├── core/
    │   ├── models.py
    │   ├── engine.py           # find_ev_opportunities; filter_min_ev
    │   ├── line_adjustment.py
    │   ├── flat_line.py
    │   ├── ev_pipeline.py
    │   ├── ev_display.py       # ranked table: Hit%, EV%, +EV, DK, FD, Src
    │   ├── ev_run_diff.py      # consecutive top-N diff vs prior ev_opportunities.json
    │   ├── pipeline_timing.py  # wall-clock stage timer for --timing
    │   └── pipeline_runner.py  # --league (case-insensitive), --min-ev, --plus-ev-only, --skip-betr/dk/fd, --timing
    ├── archive/dabble/
    ├── data/
    │   ├── processed/          # gitignored outputs
    │   └── archive/dabble/
    └── tests/
        ├── fixtures/
        └── unit/
```

**EV data flow:** `./ev` or `python -m core.pipeline_runner` → league loop (NBA, MLB) × sources (dfs: betr; books: dk, fd) → in-memory merge → `normalize.py` (master + wrapped normalized + `unified_master_board.json`) → `ev_pipeline.py` (`persist_match_diagnostics` with `by_league` → `match_report.json`; `run_ev_scan` with `run_id` check → `ev_opportunities.json`; rotate + `ev_run_diff.json`) · `scrape_coverage.json` per run


## 6. Roadmap

### Open

* **MLB props (full O/U slate):** 12 pregame markets Betr ↔ DK — see [mlb.md](docs/betting_odds/mlb.md) and `DK_MLB_STAT_CATEGORIES`. FD skipped for MLB. **Deferred v2:** `HITTER_STRIKEOUTS` (milestone-only on DK). Flat/push pitching K + milestone penalty: roadmap below.
* **MLB / DK milestone EV (v2):** Parser + engine for milestone-only tabs (over-side penalty vs devig). `HITTER_STRIKEOUTS` (`17849`); pitching K push pairing (`15221` + `17323`).
* **Additional sharp books:** Add a third sharp book (scrape → normalize → consensus); weights are env-tunable via `SHARP_BOOK_WEIGHTS_DK` / `SHARP_BOOK_WEIGHTS_FD` in `load_sharp_book_weights()`.
* **Granular promos / non-REGULAR Betr types:** Parse `MINI_BOOSTED`, `BOOSTED`, `EDGE`, etc.; store raw multipliers and alternate breakevens (wide-fetch fields already on master board).
* **Race-to-place parlay checker:** Build same parlay on DK/FD, compare to Betr promo multipliers (2-leg 3x→4x through 8-leg 100x→150x), hardcoded +EV threshold for take/pass.
* **`feat/fd-milestone-props`:** Ingest `TO_SCORE_*` / `TO_RECORD_*` / `N+_MADE_THREES` / double-double boards — master board + EV policy aligned with DK milestones (catalog in [fanduel.md](docs/betting_odds/fanduel.md)).

### Completed / archived

* Betr GraphQL scrape + parser + normalization pipeline (`betr_api.py`, wide `LeagueUpcomingEvents` fetch).
* Per-side Betr O/U EV: `allowedOptions` → parser side flags → `compare_betr_vs_draftkings` (under-only / over-only +EV when one side offered).
* DK markets API scrape via `dk_api.py` / `dk_engine.py` + `dk_parser.py` (httpx, no Playwright).
* **DK scrape hardening (Akamai 403):** per-event `fetch_event_all_markets`; `DK_MARKETS_MAX_CONCURRENT` semaphore (default 6); 403/429 retry/backoff; browser-like headers; league warm-up skipped on auto-discover — [docs/betting_odds/draftkings.md](docs/betting_odds/draftkings.md).
* `normalize.py` active platforms: Betr + DraftKings + FanDuel; Dabble archived.
* `ev_pipeline.py` loads `{betr,dk,fd}_normalized.json` → `compare_betr_vs_draftkings` → `ev_opportunities.json`; ranked plays table via `ev_display.py`.
* Offline pytest suite: `tests/unit/test_{betr,dk,fd}_*`, `test_ev_engine`, `test_ev_pipeline`, `test_ev_display`, `test_line_adjustment_multi_book`, `test_pipeline_runner`, `test_normalize`, `test_math_utils`; fixtures incl. `fd_league_nba_events.json`, `fd_event_*_player_{points,rebounds,assists}.json`.
* Betr breakeven aligned at **-120** across `math_utils`, parser side markers, and EV engine.
* Daily refresh orchestrator: `core/pipeline_runner.py` (`run_refresh`) — multi-league loop, `--dfs` / `--books` / `--leagues`, fresh-only runs with `run_id`, `core/pipeline_scrape.py`, `config/pipeline_sources.py`; repo-root `./ev` wrapper.
* Betr `--league` case normalization: `_normalize_betr_league` + `BetrEngine` uppercase GraphQL enum; GraphQL `errors` logged on invalid league — fixes empty MLB slate when invoking `./ev --league mlb`.
* Pipeline `--min-ev` / `--plus-ev-only`: filter ranked output to `ev > min_ev`; `plus_ev` flag on each row; default `min_ev=0` shows top-N including negative EV.
* Ranked plays table: `ev_display.py` — compact 10-column layout (Hit%, EV%, +EV, DK/FD O/U, Src).
* FanDuel NBA event discovery: `fd_competitions.py`, `fd_api.fetch_league_event_ids`, `probe_fd_events`, `test_fd_event_discovery`.
* FanDuel event-page props + normalization: `fd_markets.py`, `fd_engine`, `fd_parser`, `test_fd_event_page`, `test_normalize_fd`.
* FanDuel core O/U default scrape: points / rebounds / assists via `FD_DEFAULT_SCRAPE_MARKETS` (`fd_engine` + `pipeline_runner`); multi-tab fixtures and tests.
* FanDuel extended O/U scrape + grouped master board: threes / combo stats via SGP tab; `group_fd_line_rows` + parser line expansion; `FD_EXTENDED_OU_MARKETS`.
* FanDuel market catalog in [docs/betting_odds/fanduel.md](docs/betting_odds/fanduel.md): default scrape table, skipped boards, tab/SGP fetch model, core-tab fixtures.
* Multi-book consensus EV: `resolve_multi_book_sharp_quote`, `fd_exact` / `fd_alt` eligibility, `test_line_adjustment_multi_book`.
* EV run diff (consecutive `./ev`): `core/ev_run_diff.py` — rotate `ev_opportunities.json` → `ev_opportunities.previous.json`, compare top-N rows (`build_prop_key|side` buckets: new / removed / improved / fell), CLI summary after ranked table, `ev_run_diff.json`; `test_ev_run_diff.py`.
* Pipeline stage timing: `core/pipeline_timing.py` + `--timing` on `pipeline_runner` / `./ev` — wall-clock summary for scrape, normalize, and EV stages; `test_pipeline_timing.py`.
* Betr Keycloak auth probe: `python -m scrapers.dfs.betr.betr_auth` (`--try-grant`); refresh grant is the documented default — [docs/betting_odds/betr.md](docs/betting_odds/betr.md).
* Betr Keycloak `.env.example` defaults: public token URL (`account.betr.app/realms/betr/…`); `BETR_KEYCLOAK_CLIENT_ID=betr-rn` for fantasy.betr.app (refresh tokens client-bound; code default `betr-web` if unset).
* Multi-book consensus weights: `load_sharp_book_weights()` in `line_adjustment.py` — `SHARP_BOOK_WEIGHTS_DK` / `SHARP_BOOK_WEIGHTS_FD` env vars (default 1.0 each).
