# Master Project Context: Multi-Platform EV Betting Engine


**Last verified:** 2026-05-25 (update when §3, §5, or §6 change)

## 1. Project Overview

This project is a high-throughput Expected Value (+EV) sports betting engine. Its primary goal is to find profitable mathematical discrepancies by comparing fixed-payout player props on Daily Fantasy Sports (DFS) apps (primarily **Betr**) against dynamically priced, sharp sportsbook lines (**DraftKings**).

The system standardizes disparate naming conventions across books, calculates no-vig fair value on the fly, and outputs opportunities in a standardized JSON format. **Dabble** integration is archived under `backend/archive/dabble/`; capture notes remain in `docs/proxyman_dabble_setup.md`.


## 2. Tech Stack & Libraries

* **Language:** Python (async-first with `asyncio`)
* **DFS ingestion:** `httpx` for async HTTP (Betr GraphQL)
* **Sportsbook ingestion:** `httpx` async HTTP for DraftKings league/event APIs (`dk_api.py`, `dk_engine.py`); tokens via `settings.py` / env
* **Data processing:** `json`, `re`; relational array joins for DFS payloads
* **Logging:** `loguru`
* **Testing:** `pytest`, `pytest-asyncio`, `pytest-mock` (offline fixtures only)
* *(Future: FastAPI, Redis, PostgreSQL, React)*

## 3. Platform-Specific Extraction Logic

### Betr (primary DFS)

* **Access:** `fantasy.betr.app` GraphQL (`LeagueUpcomingEvents`). Bearer JWT via `BETR_BEARER_TOKEN` in `backend/config/.env` (Scrubbed Protocol: `os.getenv()` / `settings.py` only).
* **Auth:** Token is manually copied from browser DevTools today (~30-day `exp`). Roadmap: Keycloak login or refresh-token automation. See [docs/betting_odds/betr.md](docs/betting_odds/betr.md) → Authentication.
* **Scrape:** `betr_api.py` issues the GraphQL query; `betr_engine.py` / `betr_orchestrator.py` write `data/processed/betr_master_board.json` (wide fetch — see betr.md “Wide fetch policy”).
* **Data structure:** Flat relational arrays joined in `betr_parser.py` using keys like `marketId`, `selectionId`, `marketOptionId`.
* **Normalization (v1):** Only `REGULAR` projections become normalized props. Boost/edge/discount types are skipped until `prop_type` and breakeven rules exist (see parser module docstring).
* **Side availability:** Parser reads `allowedOptions` (`OVER`/`UNDER`/`MORE`/`LESS`). Sets `over_odds` / `under_odds` to **-120** only for allowed sides (availability flags for the engine). Skips empty `allowed_options` on `REGULAR` props.
* **Breakeven for EV:** `compare_betr_vs_draftkings` uses `BETR_STANDARD_BREAKEVEN_ODDS` (**-122**) from `utils/math_utils.py` for implied breakeven vs de-vigged DK prices. Product/docs often cite **-120** for standard picks — see [docs/betting_odds/betr.md](docs/betting_odds/betr.md).
* **Code:** `backend/scrapers/dfs/betr/` (`betr_api.py`, `betr_engine.py`, `betr_orchestrator.py`), `backend/parsers/betr_parser.py`.

### DraftKings (sharp sportsbook)

* **Access:** Unauthenticated `httpx` calls to DK `sportscontent` league/event/market endpoints (`config/api_headers.py` — `DK_BASE_HEADERS`, no DK token in `settings.py` today).
* **State:** URL-driven (`category` / `subcategory`); subcategory list in `config/dk_subcategories.py`.
* **Orchestration:** Resolve event IDs → dedupe → concurrent subcategory/market fetches via `dk_api.py`; `dk_engine.py` extends `base_scraper.py`.
* **Code:** `backend/scrapers/sportsbooks/dk_engine.py`, `dk_api.py`, `backend/parsers/dk_parser.py`.

### Dabble (archived)

* Archived parser/engine under `backend/archive/dabble/`. Legacy scraper: `backend/scrapers/dfs/dabble_engine.py`. Proxyman capture: [docs/proxyman_dabble_setup.md](docs/proxyman_dabble_setup.md). Fair odds: [docs/betting_odds/dabble.md](docs/betting_odds/dabble.md).

## 4. Quantitative Modeling & Math

* **Market mapping:** Platform names normalized via `PLATFORM_MARKET_MAPPINGS` → `MARKETS` in `config/market_maps.py`.
* **De-vigging:** DK American odds → implied probabilities; **multiplicative** vig removal in `utils/math_utils.py`.
* **EV calculation:** `find_ev_opportunities` / `compare_betr_vs_draftkings` in `core/engine.py` — multiplicative de-vig on DK over/under, up to one +EV row per allowed Betr side (`over_odds` / `under_odds` not `None`). Default DFS breakeven: `BETR_STANDARD_BREAKEVEN_ODDS` (-122).

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
│   │   ├── betr/               # betr_api, betr_engine, betr_orchestrator
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
│   └── ev_pipeline.py
├── archive/dabble/             # archived Dabble parser + README
├── data/
│   ├── processed/              # gitignored: *_master_board.json, *_normalized.json, ev_opportunities.json
│   └── archive/dabble/         # sample legacy board (not live pipeline)
└── tests/
    ├── fixtures/               # dk_league_*, dk_markets_* JSON
    └── unit/                   # test_betr_*, test_dk_*, test_ev_*, test_normalize, test_math_utils, archive dabble
```

**EV data flow:** Scraper → `data/processed/{betr,dk}_master_board.json` → `parsers/*` + `normalize.py` (`unified_master_board.json`, per-book normalized JSON) → `ev_pipeline.py` → `core/engine.py` → `data/processed/ev_opportunities.json`

## 6. Roadmap

### Open

* **Betr bearer token automation:** Programmatic Keycloak login or refresh so scrapes self-renew without DevTools copy.
* **Granular promos / non-REGULAR Betr types:** Parse `MINI_BOOSTED`, `BOOSTED`, `EDGE`, etc.; store raw multipliers and alternate breakevens (wide-fetch fields already on master board).
* **Betr breakeven alignment:** Reconcile -120 (docs/parser markers) vs -122 (`math_utils` EV default) if product confirms a single standard line.
* **Race-to-place parlay checker:** Build same parlay on DK/FD, compare to Betr promo multipliers (2-leg 3x→4x through 8-leg 100x→150x), hardcoded +EV threshold for take/pass.

### Completed / archived

* Betr GraphQL scrape + parser + normalization pipeline (`betr_api.py`, wide `LeagueUpcomingEvents` fetch).
* Per-side Betr O/U EV: `allowedOptions` → parser side flags → `compare_betr_vs_draftkings` (under-only / over-only +EV when one side offered).
* DK markets API scrape via `dk_api.py` / `dk_engine.py` + `dk_parser.py` (httpx, no Playwright).
* `normalize.py` active platforms: Betr + DraftKings; Dabble archived.
* `ev_pipeline.py` load normalized boards → `compare_betr_vs_draftkings` → `ev_opportunities.json`.
* Offline pytest suite: `tests/unit/test_{betr,dk}_*`, `test_ev_engine`, `test_ev_pipeline`, `test_normalize`, `test_math_utils`, fixtures under `tests/fixtures/`.
