# Master Project Context: Multi-Platform EV Betting Engine


**Last verified:** 2026-05-25 (ops automation: pipeline_runner, betr_auth)

## 1. Project Overview

This project is a high-throughput Expected Value (+EV) sports betting engine. Its primary goal is to find profitable mathematical discrepancies by comparing fixed-payout player props on Daily Fantasy Sports (DFS) apps (primarily **Betr**) against dynamically priced, sharp sportsbook lines (**DraftKings**).

The system standardizes disparate naming conventions across books, calculates no-vig fair value on the fly, and outputs opportunities in a standardized JSON format. **Dabble** integration is archived under `backend/archive/dabble/`; capture notes remain in `docs/proxyman_dabble_setup.md`.


## 2. Tech Stack & Libraries

* **Language:** Python (async-first with `asyncio`)
* **DFS ingestion:** `httpx` for async HTTP (Betr GraphQL)
* **Sportsbook ingestion:** `httpx` async HTTP for DraftKings league/event/market APIs (`dk_api.py`, `dk_engine.py`); headers via `api_headers.py` (no DK credential in `settings.py` today)
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
* **Orchestration:** Resolve event IDs → dedupe → concurrent subcategory/market fetches via `dk_api.py`; `dk_engine.py` extends `base_scraper.py`. `dk_api` ingests main and alternate point lines (`is_main_line` on master board rows).
* **Line alignment:** `core/line_adjustment.py` maps DK prices onto each Betr line (exact alt, interpolated bracket, or extrapolated single-anchor). **+EV ranking** only uses `exact`, `dk_alt`, and `dk_interpolated` O/U (`is_ev_eligible_quote`); extrapolated and milestone quotes are diagnostics-only (`no_exact_sharp_line` in match stats) until FanDuel multi-book exact alts land. See [docs/betting_odds/draftkings.md](docs/betting_odds/draftkings.md).
* **Flat Betr lines:** Integer lines (push risk) skipped by default; `--include-flat-lines` uses `core/flat_line.py` adjusted breakeven.
* **Code:** `backend/scrapers/sportsbooks/dk_engine.py`, `dk_api.py`, `backend/parsers/dk_parser.py`.

### Dabble (archived)

* Archived parser/engine under `backend/archive/dabble/`. Legacy scraper: `backend/scrapers/dfs/dabble_engine.py`. Proxyman capture: [docs/proxyman_dabble_setup.md](docs/proxyman_dabble_setup.md). Fair odds: [docs/betting_odds/dabble.md](docs/betting_odds/dabble.md).

## 4. Quantitative Modeling & Math

* **Market mapping:** Platform names normalized via `PLATFORM_MARKET_MAPPINGS` → `MARKETS` in `config/market_maps.py`.
* **De-vigging:** DK American odds → implied probabilities; **multiplicative** vig removal in `utils/math_utils.py`.
* **EV calculation:** `find_ev_opportunities` / `compare_betr_vs_draftkings` in `core/engine.py` — resolve DK to Betr line via `line_adjustment.py`, skip non-exact sharp quotes, multiplicative de-vig on eligible O/U only, one row per allowed Betr side, ranked by EV; output capped at `top_n` (default 15) with `plus_ev` when edge exceeds `min_ev`. Default DFS breakeven: `BETR_STANDARD_BREAKEVEN_ODDS` (-120); flat integer Betr lines optional (`--include-flat-lines`).

## 5. Architecture & File Structure

Decoupled layout under `backend/`:

```text
backend/
├── config/
│   ├── api_headers.py
│   ├── market_maps.py
│   ├── settings.py
│   ├── dk_subcategories.py
│   └── .env                    # local secrets (gitignored)
├── utils/
│   ├── math_utils.py
│   └── formatting.py
├── scrapers/
│   ├── base_scraper.py
│   ├── dfs/
│   │   ├── betr/               # betr_api, betr_auth, betr_engine, betr_orchestrator
│   │   └── dabble_engine.py    # legacy
│   └── sportsbooks/
│       ├── dk_engine.py
│       └── dk_api.py
├── parsers/
│   ├── betr_parser.py
│   ├── dk_parser.py
│   └── normalize.py
├── core/
│   ├── models.py
│   ├── engine.py
│   ├── ev_pipeline.py
│   └── pipeline_runner.py      # run_refresh CLI: scrape → normalize → EV
├── archive/dabble/             # archived Dabble parser + README
├── data/
│   ├── processed/              # gitignored: boards, ev_opportunities.json, match_report.json, unmatched_*.json
│   └── archive/dabble/         # sample legacy board (not live pipeline)
└── tests/
    ├── fixtures/               # dk_league_*, dk_markets_* JSON
    └── unit/                   # test_betr_*, test_dk_*, test_ev_*, test_normalize, test_math_utils, archive dabble
```

**EV data flow:** `python -m core.pipeline_runner` (or per-stage CLIs) → scrapers → `data/processed/{betr,dk}_master_board.json` → `normalize.py` → `ev_pipeline.py` (`persist_match_diagnostics` → `match_report.json`, `unmatched_*.json`) → `core/engine.py` → `data/processed/ev_opportunities.json`

## 6. Roadmap

### Open

* **FanDuel sharp + multi-book exact alts:** Scrape/normalize FD O/U ladders; consensus de-vig across DK + FD only when each book has an exact line match (no extrapolation in +EV). Planned under `scrapers/sportsbooks/` + `resolve_sharp_quote` multi-book extension. Once alt ladders exist, compare `dk_extrapolated` vs exact alts (e.g. Fox 13.5) to calibrate logit-per-point slope — diagnostics only until then.
* **Betr Keycloak discovery:** Confirm `BETR_KEYCLOAK_TOKEN_URL` / client id from a captured login if password grant fails out of the box.
* **Granular promos / non-REGULAR Betr types:** Parse `MINI_BOOSTED`, `BOOSTED`, `EDGE`, etc.; store raw multipliers and alternate breakevens (wide-fetch fields already on master board).
* **Race-to-place parlay checker:** Build same parlay on DK/FD, compare to Betr promo multipliers (2-leg 3x→4x through 8-leg 100x→150x), hardcoded +EV threshold for take/pass.

### Completed / archived

* Betr GraphQL scrape + parser + normalization pipeline (`betr_api.py`, wide `LeagueUpcomingEvents` fetch).
* Per-side Betr O/U EV: `allowedOptions` → parser side flags → `compare_betr_vs_draftkings` (under-only / over-only +EV when one side offered).
* DK markets API scrape via `dk_api.py` / `dk_engine.py` + `dk_parser.py` (httpx, no Playwright).
* `normalize.py` active platforms: Betr + DraftKings; Dabble archived.
* `ev_pipeline.py` load normalized boards → `compare_betr_vs_draftkings` → `ev_opportunities.json`.
* Offline pytest suite: `tests/unit/test_{betr,dk}_*`, `test_ev_engine`, `test_ev_pipeline`, `test_normalize`, `test_math_utils`, fixtures under `tests/fixtures/`.
* Betr breakeven aligned at **-120** across `math_utils`, parser side markers, and EV engine.
* Daily refresh orchestrator: `core/pipeline_runner.py` (`run_refresh`) with JWT expiry guard and optional Keycloak refresh via `betr_auth.py`.
