# Master Project Context: Multi-Platform EV Betting Engine


**Last verified:** 2026-05-26 (update when §3, §5, or §6 change)

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
* **Data structure:** Flat relational arrays joined in `betr_parser.py` using keys like `marketId`, `selectionId`, `marketOptionId`.
* **Side availability:** Parser reads `allowedOptions` (`OVER`/`UNDER`/`MORE`/`LESS`). EV engine only evaluates sides Betr actually offers; empty `allowed_options` on `REGULAR` props are skipped.
* **Breakeven:** Standard picks use **-120** (54.55% implied) vs de-vigged DK fair value. Boost/edge types documented in `docs/betting_odds/betr.md`.
* **Code:** `backend/scrapers/dfs/betr/` (`betr_api.py`, `betr_engine.py`, `betr_orchestrator.py`), `backend/parsers/betr_parser.py`.

### DraftKings (sharp sportsbook)

* **Access:** Authenticated `httpx` calls to DK league/event endpoints; bearer tokens in `backend/config/.env` (see `settings.py`).
* **State:** URL-driven (`category` / `subcategory`); subcategory list in `config/dk_subcategories.py`.
* **Orchestration:** Resolve event IDs → dedupe → concurrent subcategory/market fetches via `dk_api.py`.
* **Code:** `backend/scrapers/sportsbooks/dk_engine.py`, `dk_api.py`, `backend/parsers/dk_parser.py`.

### Dabble (archived)

* Archived parser/engine under `backend/archive/dabble/`. Legacy scraper: `backend/scrapers/dfs/dabble_engine.py`. Proxyman capture: [docs/proxyman_dabble_setup.md](docs/proxyman_dabble_setup.md). Fair odds: [docs/betting_odds/dabble.md](docs/betting_odds/dabble.md).

## 4. Quantitative Modeling & Math

* **Market mapping:** Platform names normalized via `PLATFORM_MARKET_MAPPINGS` → `MARKETS` in `config/market_maps.py`.
* **De-vigging:** DK American odds → implied probabilities; **multiplicative** vig removal in `utils/math_utils.py`.
* **EV calculation:** Fair probability vs DFS breakeven (`compare_betr_vs_draftkings` in `core/engine.py`). Betr uses -120 baseline for standard lines.

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
├── archive/dabble/             # archived Dabble parser
├── data/processed/             # gitignored scrape + EV output
└── tests/
    ├── fixtures/
    └── unit/
```

**EV data flow:** Scraper raw JSON → platform parser → `normalize.py` → `ev_pipeline.py` → `core/engine.py` → `data/processed/ev_opportunities.json`

## 6. Roadmap

### Open

* **Betr bearer token automation:** Programmatic Keycloak login or refresh so scrapes self-renew without DevTools copy.
* **Granular promos:** Store raw multipliers (e.g. 1.1x, 0.7x) per prop instead of a generic boost tag.
* **Betr O/U on normal props:** Board should respect `allowedOptions` for both sides (e.g. under-only +EV when Betr only lists over).
* **Race-to-place parlay checker:** Build same parlay on DK/FD, compare to Betr promo multipliers (2-leg 3x→4x through 8-leg 100x→150x), hardcoded +EV threshold for take/pass.

### Completed / archived

* Betr GraphQL scrape + parser + normalization pipeline.
* DK API scrape via `dk_api.py` / `dk_engine.py` + parser.
* `ev_pipeline.py` unified board → split by book → EV output JSON.
