# Master Project Context: Multi-Platform EV Betting Engine


**Last verified:** 2026-05-26 (`./ev` CLI, `--min-ev` / `--plus-ev-only` output filter)

## 1. Project Overview

This project is a high-throughput Expected Value (+EV) sports betting engine. Its primary goal is to find profitable mathematical discrepancies by comparing fixed-payout player props on Daily Fantasy Sports (DFS) apps (primarily **Betr**) against dynamically priced sharp sportsbook lines (**DraftKings**, **FanDuel**).

The system standardizes disparate naming conventions across books, calculates no-vig fair value on the fly, and outputs opportunities in a standardized JSON format. **Dabble** integration is archived under `backend/archive/dabble/`; capture notes remain in `docs/proxyman_dabble_setup.md`.


## 2. Tech Stack & Libraries

* **Language:** Python (async-first with `asyncio`)
* **DFS ingestion:** `httpx` for async HTTP (Betr GraphQL)
* **Sportsbook ingestion:** `httpx` async HTTP for DraftKings league/event/market APIs (`dk_api.py`, `dk_engine.py`) and FanDuel league + event-page APIs (`fd_api.py`, `fd_engine.py`); headers via `api_headers.py` (`DK_*`, `FD_*`; no sportsbook bearer in `settings.py` today)
* **Data processing:** `json`, `re`; relational array joins for DFS payloads
* **Logging:** `loguru`
* **Testing:** `pytest`, `pytest-asyncio`, `pytest-mock` (offline fixtures only)
* *(Future: FastAPI, Redis, PostgreSQL, React)*

## 3. Platform-Specific Extraction Logic

### Betr (primary DFS)

* **Access:** `fantasy.betr.app` GraphQL (`LeagueUpcomingEvents`). Bearer JWT via `BETR_BEARER_TOKEN` in `backend/config/.env` (Scrubbed Protocol: `os.getenv()` / `settings.py` only).
* **Auth:** `betr_auth.py` — JWT expiry pre-flight, optional Keycloak password/refresh grant (`BETR_USERNAME` / `BETR_REFRESH_TOKEN` + `BETR_KEYCLOAK_TOKEN_URL`), fallback to manual `BETR_BEARER_TOKEN`. See [docs/betting_odds/betr.md](docs/betting_odds/betr.md) → Authentication.
* **Scrape:** `betr_api.py` issues the GraphQL query; `betr_engine.py` / `betr_orchestrator.py` write `data/processed/betr_master_board.json` (wide fetch — see betr.md “Wide fetch policy”).
* **Data structure:** Flat relational arrays joined in `betr_parser.py` using keys like `marketId`, `selectionId`, `marketOptionId`.
* **Normalization (v1):** Only `REGULAR` projections become normalized props. Boost/edge/discount types are skipped until `prop_type` and breakeven rules exist (see parser module docstring).
* **Side availability:** Parser reads `allowedOptions` (`OVER`/`UNDER`/`MORE`/`LESS`). Sets `over_odds` / `under_odds` to **-120** only for allowed sides (availability flags for the engine). Skips empty `allowed_options` on `REGULAR` props.
* **Breakeven for EV:** `compare_betr_vs_draftkings` uses `BETR_STANDARD_BREAKEVEN_ODDS` (**-120**, 54.55% implied) from `utils/math_utils.py` for standard REGULAR picks — see [docs/betting_odds/betr.md](docs/betting_odds/betr.md).
* **Code:** `backend/scrapers/dfs/betr/` (`betr_api.py`, `betr_engine.py`, `betr_orchestrator.py`), `backend/parsers/betr_parser.py`.

### DraftKings (sharp sportsbook)

* **Access:** Unauthenticated `httpx` calls to DK `sportscontent` league/event/market endpoints (`config/api_headers.py` — `DK_BASE_HEADERS`, no DK token in `settings.py` today).
* **State:** URL-driven (`category` / `subcategory`); subcategory list in `config/dk_subcategories.py` (core stats + O/U extended: `threes`, `steals`, `blocks`, `stl+blk`; milestone 1+/2+/3+ fallback via `DK_MILESTONE_STAT_CATEGORIES`; pending Betr markets in `DK_PENDING_STAT_CATEGORIES`).
* **Orchestration:** Resolve event IDs → dedupe → per-event parallel subcategory fetches via `fetch_event_all_markets` (`dk_api.py`); global semaphore `DK_MARKETS_MAX_CONCURRENT` (default 6, env-tunable); transient 403/429 retries with backoff; browser-like headers in `api_headers.py`. League slate warm-up skipped on auto-discover. `dk_engine.py` extends `base_scraper.py`. `dk_api` ingests main and alternate point lines (`is_main_line` on master board rows).
* **Line alignment:** `core/line_adjustment.py` maps DK prices onto each Betr line (exact alt, interpolated bracket, or extrapolated single-anchor). **+EV ranking** uses `exact`, `dk_alt`, `dk_interpolated`, and (with FanDuel loaded) `fd_exact`, `fd_alt`, `multi_book_consensus`; extrapolated and milestone DK quotes stay diagnostics-only. See [docs/betting_odds/draftkings.md](docs/betting_odds/draftkings.md).
* **Flat Betr lines:** Integer lines (push risk) skipped by default; `--include-flat-lines` uses `core/flat_line.py` adjusted breakeven.
* **Code:** `backend/scrapers/sportsbooks/dk_engine.py`, `dk_api.py`, `backend/parsers/dk_parser.py`.

### FanDuel (sharp sportsbook)

* **Access:** State-specific `sbapi.{state}.sportsbook.fanduel.com` — `FD_SPORTSBOOK_API_HOST` in `config/.env` (default `https://sbapi.nj.sportsbook.fanduel.com`). Public web client key `_ak` via `FD_API_KEY` (see `config/.env.example`). No bearer token for league/event JSON today.
* **Event discovery:** `GET /api/content-managed-page` with `customPageId=nba` → `attachments.events`. Scrapable matchups: NBA `competitionId=10547864` (not futures `12739957`) and name contains ` @ `. Helpers in `config/fd_competitions.py`; live fetch in `fd_api.fetch_league_event_ids`.
* **Event-page props:** `GET /api/event-page` per matchup × tab → `fd_engine` → `fd_master_board.json`. Tab map and default scrape list in `config/fd_markets.py` (`FD_TAB_CANONICAL_MARKETS`, `FD_DEFAULT_SCRAPE_MARKETS`); full canonical ↔ tab ↔ `marketType` table in [docs/betting_odds/fanduel.md](docs/betting_odds/fanduel.md). **Core O/U:** `points` / `rebounds` / `assists` — one dedicated tab each (`player-points`, `player-rebounds`, `player-assists`). **Extended O/U:** `threes`, `pts+reb`, `pts+ast`, `pra`, `reb+ast` — one filtered fetch of `same-game-parlay-` per event (`scrape_targets_for_markets`). O/U detection: `parse_player_ou_market_type` (`PLAYER_[A-Z]_(ALT_)?TOTAL_*` → canonical suffix map). Main + alt ladders flattened; `group_fd_line_rows` groups alt steps under one prop per player/market; `fd_parser` expands `lines` for normalization. **In-play** events skipped in flatten (`event_page_in_play`).
* **Not scraped (catalogued in fanduel.md):** milestones (`TO_SCORE_*`, `TO_RECORD_*`, `N+_MADE_THREES`, double/triple-double), quarter/half props, game lines (`MONEY_LINE`, totals, spreads). **Steals/blocks O/U not observed** on FD NBA event pages (2026-05-26 probe). Milestone EV unlike DK today — see roadmap `feat/fd-milestone-props`.
* **Normalization:** `fd_parser.py` + `market_maps.py` → `fd_normalized.json` (with Betr/DK via `normalize.py`).
* **EV / multi-book:** `resolve_multi_book_sharp_quote` in `line_adjustment.py` — equal-weight de-vig when DK and FD both have exact O/U at the Betr line; otherwise FD exact-only or DK ladder methods. `compare_betr_vs_draftkings(..., fanduel_props=)` in `engine.py`.
* **Probe (live):** `python -m scripts.probe_fd_events --league nba` — optional `--event-id`, `--game-url`, `--tab`, `--raw`. Offline: `test_fd_event_discovery`, `test_fd_event_page`; fixtures `fd_event_*_player_{points,rebounds,assists}.json` (SGP / extended O/U fixture TBD — live `probe_fd_events --tab same-game-parlay-`).
* **Pipeline:** `pipeline_runner` (or repo-root `./ev`) runs Betr + DK + FD scrapes in parallel (`_run_selected_scrapes`); `--skip-betr` / `--skip-dk` / `--skip-fd` skip that book’s scrape and JWT (Betr only), reusing existing normalized boards for EV.
* **Code:** `backend/config/fd_competitions.py`, `fd_markets.py`, `backend/scrapers/sportsbooks/fd_api.py`, `fd_engine.py`, `backend/parsers/fd_parser.py`, `backend/scripts/probe_fd_events.py`. **Docs:** [docs/betting_odds/fanduel.md](docs/betting_odds/fanduel.md).

### Dabble (archived)

* Archived parser/engine under `backend/archive/dabble/`. Legacy scraper: `backend/scrapers/dfs/dabble_engine.py`. Proxyman capture: [docs/proxyman_dabble_setup.md](docs/proxyman_dabble_setup.md). Fair odds: [docs/betting_odds/dabble.md](docs/betting_odds/dabble.md).

## 4. Quantitative Modeling & Math

* **Market mapping:** Platform names normalized via `PLATFORM_MARKET_MAPPINGS` → `MARKETS` in `config/market_maps.py`.
* **De-vigging:** DK American odds → implied probabilities; **multiplicative** vig removal in `utils/math_utils.py`.
* **EV calculation:** `find_ev_opportunities` / `compare_betr_vs_draftkings` in `core/engine.py` — resolve sharp quote per Betr line via `line_adjustment.py` (DK ladder, optional FD exact, optional `multi_book_consensus`), multiplicative de-vig on eligible O/U, one row per allowed Betr side, ranked by EV. Each row gets `plus_ev` when `ev > min_ev`. Optional `filter_min_ev` drops sub-threshold rows before `top_n` (pipeline: auto when `--min-ev > 0`, or `--plus-ev-only` with any `--min-ev`). `run_ev_scan` logs a ranked plays table (`core/ev_display.py`: Hit%, EV%, +EV, DK/FD O/U, `line_source` — compact widths) plus run-over-run diff (`core/ev_run_diff.py`: new / removed / improved / fell vs prior top-N). JSON output capped at `top_n` (default 15). Default DFS breakeven: `BETR_STANDARD_BREAKEVEN_ODDS` (-120); flat integer Betr lines optional (`--include-flat-lines`).

## 5. Architecture & File Structure

```text
ev-sports-tracker/
├── ev                            # bash wrapper → backend pipeline_runner (same flags)
└── backend/
    ├── config/
    │   ├── api_headers.py
    │   ├── market_maps.py
    │   ├── settings.py
    │   ├── dk_subcategories.py
    │   ├── fd_competitions.py
    │   ├── fd_markets.py       # tab ↔ canonical; FD_DEFAULT_SCRAPE_MARKETS; parse_player_ou_market_type
    │   ├── .env.example        # optional FD_SPORTSBOOK_API_HOST, FD_API_KEY
    │   └── .env                # local secrets (gitignored)
    ├── scripts/
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
    │   └── pipeline_runner.py  # --min-ev, --plus-ev-only, --skip-betr/dk/fd
    ├── archive/dabble/
    ├── data/
    │   ├── processed/          # gitignored outputs
    │   └── archive/dabble/
    └── tests/
        ├── fixtures/
        └── unit/
```

**EV data flow:** `./ev` or `python -m core.pipeline_runner` from `backend/` → scrapers → `data/processed/{betr,dk,fd}_master_board.json` → `normalize.py` → `{betr,dk,fd}_normalized.json` → `ev_pipeline.py` (`persist_match_diagnostics` → `match_report.json`, `unmatched_*.json`; `run_ev_scan` → ranked table + `ev_opportunities.json` via `engine.py`; rotate prior output to `ev_opportunities.previous.json`, CLI run-diff summary + `ev_run_diff.json` via `ev_run_diff.py`)

## 6. Roadmap

### Open

* **Additional sharp books:** Revisit `SHARP_BOOK_WEIGHTS` in `line_adjustment.py` before adding a third book beyond DK + FD.
* **Betr Keycloak discovery:** Confirm `BETR_KEYCLOAK_TOKEN_URL` / client id from a captured login if password grant fails out of the box.
* **Granular promos / non-REGULAR Betr types:** Parse `MINI_BOOSTED`, `BOOSTED`, `EDGE`, etc.; store raw multipliers and alternate breakevens (wide-fetch fields already on master board).
* **Race-to-place parlay checker:** Build same parlay on DK/FD, compare to Betr promo multipliers (2-leg 3x→4x through 8-leg 100x→150x), hardcoded +EV threshold for take/pass.
* **`feat/fd-milestone-props`:** Ingest `TO_SCORE_*` / `TO_RECORD_*` / `N+_MADE_THREES` / double-double boards — master board + EV policy aligned with DK milestones (catalog in [fanduel.md](docs/betting_odds/fanduel.md)).

### Completed / archived

* Betr GraphQL scrape + parser + normalization pipeline (`betr_api.py`, wide `LeagueUpcomingEvents` fetch).
* Per-side Betr O/U EV: `allowedOptions` → parser side flags → `compare_betr_vs_draftkings` (under-only / over-only +EV when one side offered).
* DK markets API scrape via `dk_api.py` / `dk_engine.py` + `dk_parser.py` (httpx, no Playwright).
* `normalize.py` active platforms: Betr + DraftKings + FanDuel; Dabble archived.
* `ev_pipeline.py` loads `{betr,dk,fd}_normalized.json` → `compare_betr_vs_draftkings` → `ev_opportunities.json`; ranked plays table via `ev_display.py`.
* Offline pytest suite: `tests/unit/test_{betr,dk,fd}_*`, `test_ev_engine`, `test_ev_pipeline`, `test_ev_display`, `test_line_adjustment_multi_book`, `test_pipeline_runner`, `test_normalize`, `test_math_utils`; fixtures incl. `fd_league_nba_events.json`, `fd_event_*_player_{points,rebounds,assists}.json`.
* Betr breakeven aligned at **-120** across `math_utils`, parser side markers, and EV engine.
* Daily refresh orchestrator: `core/pipeline_runner.py` (`run_refresh`) — parallel scrapes, `--skip-betr` / `--skip-dk` / `--skip-fd`, JWT pre-flight via `betr_auth.py`; repo-root `./ev` wrapper.
* Pipeline `--min-ev` / `--plus-ev-only`: filter ranked output to `ev > min_ev`; `plus_ev` flag on each row; default `min_ev=0` shows top-N including negative EV.
* Ranked plays table: `ev_display.py` — compact 10-column layout (Hit%, EV%, +EV, DK/FD O/U, Src).
* FanDuel NBA event discovery: `fd_competitions.py`, `fd_api.fetch_league_event_ids`, `probe_fd_events`, `test_fd_event_discovery`.
* FanDuel event-page props + normalization: `fd_markets.py`, `fd_engine`, `fd_parser`, `test_fd_event_page`, `test_normalize_fd`.
* FanDuel core O/U default scrape: points / rebounds / assists via `FD_DEFAULT_SCRAPE_MARKETS` (`fd_engine` + `pipeline_runner`); multi-tab fixtures and tests.
* FanDuel extended O/U scrape + grouped master board: threes / combo stats via SGP tab; `group_fd_line_rows` + parser line expansion; `FD_EXTENDED_OU_MARKETS`.
* FanDuel market catalog in [docs/betting_odds/fanduel.md](docs/betting_odds/fanduel.md): default scrape table, skipped boards, tab/SGP fetch model, core-tab fixtures.
* Multi-book consensus EV: `resolve_multi_book_sharp_quote`, `fd_exact` / `fd_alt` eligibility, `test_line_adjustment_multi_book`.
* EV run diff (consecutive `./ev`): `core/ev_run_diff.py` — rotate `ev_opportunities.json` → `ev_opportunities.previous.json`, compare top-N rows (`build_prop_key|side` buckets: new / removed / improved / fell), CLI summary after ranked table, `ev_run_diff.json`; `test_ev_run_diff.py`.
