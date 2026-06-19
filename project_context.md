# Master Project Context: Multi-Platform EV Betting Engine


**Last verified:** 2026-06-18 (milestone `N+` admission onto +EV board — hold-aware de-vig + dynamic fair-over gate in `line_adjustment.py`; `ms🔶` Src badge)

## 1. Project Overview

This project is a high-throughput Expected Value (+EV) sports betting engine. Its primary goal is to find profitable mathematical discrepancies by comparing fixed-payout player props on Daily Fantasy Sports (DFS) apps (primarily **Betr**) against dynamically priced sharp sportsbook lines (**DraftKings**, **FanDuel**).

The system standardizes disparate naming conventions across books, calculates no-vig fair value on the fly, and outputs opportunities in a standardized JSON format. **Dabble** integration is archived under `backend/archive/dabble/`; mobile-only Proxyman capture notes (not used for Betr/DK/FD) remain in `docs/proxyman_dabble_setup.md`.


## 2. Tech Stack & Libraries

* **Language:** Python (async-first with `asyncio`)
* **DFS ingestion:** `httpx` for async HTTP (Betr GraphQL)
* **Sportsbook ingestion:** `httpx` async HTTP for DraftKings league/event/market APIs (`dk_api.py`, `dk_engine.py`) and FanDuel league + event-page APIs (`fd_api.py`, `fd_engine.py`); headers via `api_headers.py` (`BETR_*`, `DK_*`, `FD_*`; Betr JWT in `settings.py` / `betr_auth`; DK/FD no sportsbook bearer today)
* **Data processing:** `json`, `re`; relational array joins for DFS payloads
* **Logging:** `loguru`
* **Testing:** `pytest`, `pytest-asyncio`, `pytest-mock` (offline fixtures only)
* *(Future: FastAPI, Redis, PostgreSQL, React)*

## 3. Platform-Specific Extraction Logic

Platform detail lives in [docs/betting_odds/](docs/betting_odds/). Summary below; each doc covers auth, scrape policy, markets, probes, and EV hooks.

### Betr (primary DFS)

* **Role:** Fixed-payout DFS props compared to sharp books.
* **Code:** `backend/scrapers/dfs/betr/`, `backend/parsers/betr_parser.py`
* **Detail:** [docs/betting_odds/betr.md](docs/betting_odds/betr.md) — GraphQL auth, **app-parity request headers** (`jurisdiction`, `channel`, `fantasy-api-version`, etc. in `BETR_BASE_HEADERS`; override via `BETR_JURISDICTION` and related env vars), wide fetch, `REGULAR` / `allowedOptions`, -120 breakeven.
* **Probe:** `python -m scrapers.dfs.betr.betr_api [LEAGUE]` — standalone `LeagueUpcomingEvents` fetch (default `NBA`; uppercase enum e.g. `WNBA`, `MLB`); saves `data/processed/betr_league_upcoming_events_raw.json`; logs event `status` mix and `isLive` projection counts.
* **Live (MLB runs):** Same `LeagueUpcomingEvents` → `getUpcomingEventsV2` operation returns scheduled + `IN_PROGRESS` when client headers match `picks.betr.app` DevTools (without `jurisdiction` / `channel` / fantasy API versions the API may return pregame-only). Engine merges via `extract_raw_props` / `iter_live_events` (`BETR_LIVE_EVENT_STATUSES`); live projections require `marketStatus == OPENED` and `isLive == true`; master board and parser propagate `is_live`. `BetrEngine.scrape` logs scheduled/live counts and warns when zero live events during a live slate.

### DraftKings (sharp sportsbook)

* **Role:** Sharp O/U ladders and milestone (`N+`) fallbacks; primary input to `line_adjustment.py`.
* **Milestones:** DK is the only sharp book that emits `line_kind == "milestone"` today (FanDuel skips `TO_SCORE_*` / similar). Exact milestone overs at the Betr line (`dk_milestone_exact`) can reach the +EV board when hold-aware de-vig clears `MILESTONE_MIN_FAIR_OVER` (default −160 fair over); interpolated/extrapolated milestones stay off the board. De-vig: contiguous `N+` ladder normalization, else hold-shrink from sibling O/U hold (`estimate_ou_hold`) or `MILESTONE_ASSUMED_HOLD`. Admitted rows flagged `not_true_devig` / `milestone_devig_method` in JSON; CLI **Src** shows `ms🔶`. Logic is book-agnostic (milestone ladder = union of sharp-book milestone props; `sharp_books` = source book).
* **Code:** `dk_engine.py`, `dk_api.py`, `dk_parser.py`, `config/dk_subcategories.py`, `scrapers/sportsbooks/dk_subcategory_discovery.py`
* **Detail:** [docs/betting_odds/draftkings.md](docs/betting_odds/draftkings.md) — slates, subcategories, eligible `line_source` values.
* **Config:** `DK_NBA_*_STAT_CATEGORIES` (NBA O/U + milestones); `DK_WNBA_*` aliases same prop IDs with slate `94682` / `4511`; `DK_MLB_STAT_CATEGORIES` / `DK_MLB_LIVE_STAT_CATEGORIES` (MLB pregame + live batter tabs via `stat_categories_for_league` / `live_stat_categories_for_league`).
* **Live (MLB):** League slate discovers pregame (`NOT_STARTED`) and live (`IN_PROGRESS`, `STARTED` in `LIVE_EVENT_STATUSES`) events; live events scrape `configured_live_stat_categories_for_league` (`DK_MLB_LIVE_STAT_CATEGORIES` — full 8-market batter O/U set incl. `walks` live `9536` vs pregame `17411`). Live subCategoryIds often differ from pregame (probe: `probe_dk_subcategories <live_event_id> --league mlb --live --discover`). Unset live IDs skip that market on in-game events. DK rows tagged `is_live`; parser propagates.

### FanDuel (sharp sportsbook)

* **Role:** Second sharp book; multi-book consensus when DK+FD align at the Betr line. **NBA** (per-stat tabs + SGP extended O/U). **MLB** pregame O/U (`FD_LEAGUE_SLATES["mlb"]`; `pitcher-props` / `batter-props` tabs — `PITCHER_*` / `BATTER_*` `TOTAL_*` marketTypes; 13-market scrape via per-league `fd_markets` / `fd_competitions` dispatch). Pregame only — no live FD MLB scrape. Milestones deliberately skipped at scrape (`fd_api`); when FD adds milestone props, they flow through the same book-agnostic milestone path in `line_adjustment.py`.
* **Parser:** `fd_parser.py` expands grouped `lines` ladders to line-level `fd_normalized.json` rows; copies `league` from the grouped master-board parent (set in `fd_engine`) so `build_prop_key` can match Betr/DK by league.
* **Code:** `fd_api.py`, `fd_engine.py`, `fd_parser.py`, `config/fd_markets.py`, `config/fd_competitions.py`, `scripts/probe_fd_events.py`
* **Detail:** [docs/betting_odds/fanduel.md](docs/betting_odds/fanduel.md) — event discovery, tabs, O/U vs milestones.

### Dabble (archived)

* **Code:** `backend/archive/dabble/` · **Detail:** [docs/betting_odds/dabble.md](docs/betting_odds/dabble.md) · mobile-only capture: [docs/proxyman_dabble_setup.md](docs/proxyman_dabble_setup.md)

### MLB

* **Detail:** [docs/betting_odds/mlb.md](docs/betting_odds/mlb.md) — pregame 13-market O/U slate (`DK_MLB_STAT_CATEGORIES`, incl. `doubles`) plus live batter O/U (`DK_MLB_LIVE_STAT_CATEGORIES` — all 8 batter live IDs set, e.g. `walks` `9536` live vs `17411` pregame; live IDs differ from pregame on many tabs). FanDuel MLB: same 13-market pregame O/U list (pitcher + batter tabs); `./ev --mlb --books fd` or full `--mlb` Betr ↔ (DK + FD) consensus. EV output rows include `is_live` (ranked table **Live** column). No CLI flag — DK and Betr live discovery are standing behavior on `./ev --leagues mlb` (Betr: app-parity GraphQL headers; DK: `DK_MLB_LIVE_STAT_CATEGORIES`).

### WNBA

* **Detail:** Pregame only — Betr wide fetch (`League!` = `WNBA`) vs DK sharp (`DK_LEAGUE_SLATES["wnba"]`, NBA-parity O/U + milestone fallback IDs via `DK_WNBA_*`). FanDuel auto-skipped (no `FD_LEAGUE_SLATES` entry). CLI: `./ev --wnba` or `--leagues wnba`. Betr probe: `python -m scrapers.dfs.betr.betr_api WNBA`.

## 4. Quantitative Modeling & Math

* **Market mapping:** Platform names normalized via `PLATFORM_MARKET_MAPPINGS` → `MARKETS` in `config/market_maps.py`.
* **De-vigging:** O/U — DK/FD American odds → implied probabilities; **multiplicative** vig removal in `utils/math_utils.py`. Milestone (`N+`, over-only) — `devig_milestone_fair_over` in `line_adjustment.py`: ladder-normalization on contiguous thresholds, else hold-shrink using observed O/U hold (`estimate_ou_hold`) or `MILESTONE_ASSUMED_HOLD`; admission floor `MILESTONE_MIN_FAIR_OVER` (env-tunable in `settings.py`).
* **EV calculation:** `find_ev_opportunities` / `compare_betr_vs_draftkings` in `core/engine.py` — resolve sharp quote per Betr line via `line_adjustment.py` (O/U ladder first; optional FD exact + `multi_book_consensus`; milestone gap-filler when O/U missing or extrapolated only). Eligible O/U: multiplicative de-vig. Eligible milestone: exact threshold only, post-de-vig fair over must clear gate. One row per allowed Betr side, ranked by EV. Each row gets `plus_ev` when `ev > min_ev`. Optional `filter_min_ev` drops sub-threshold rows before `top_n` (pipeline: auto when `--min-ev > 0`, or `--plus-ev-only` with any `--min-ev`). `run_ev_scan` logs a ranked plays table (`core/ev_display.py`: Lg, Hit%, EV%, DK/FD O/U, `line_source` — compact widths; milestone exact → `ms🔶`) plus run-over-run diff (`core/ev_run_diff.py`: new / removed / improved / fell vs prior top-N). JSON output capped at `top_n` (default 15). Milestone rows carry `milestone_admitted`, `milestone_devig_method`, `not_true_devig`, and vig caveats. Default DFS breakeven: `BETR_STANDARD_BREAKEVEN_ODDS` (-120); flat integer Betr lines optional (`--include-flat-lines`).

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
    │   ├── api_headers.py      # BETR_BASE_HEADERS (jurisdiction/channel/fantasy-api-version); DK_*; FD_*
    │   ├── market_maps.py
    │   ├── settings.py           # SHARP_BOOK_WEIGHTS_*; MILESTONE_MIN_FAIR_OVER / MILESTONE_ASSUMED_HOLD
    │   ├── dk_subcategories.py   # DK_NBA_* / DK_WNBA_* / DK_MLB_* STAT_CATEGORIES; DK_MLB_LIVE_STAT_CATEGORIES
    │   ├── dk_discovery.py       # ID scan ranges; DK_MLB_LIVE_DISCOVERY_ID_RANGES; discovery output paths
    │   ├── discovery/          # per-league progress manifests (mlb.yaml)
    │   ├── fd_competitions.py  # FD_LEAGUE_SLATES; per-league event tab labels
    │   ├── fd_markets.py       # per-league tab/market dispatch (*_for_league); NBA + MLB O/U parse
    │   ├── pipeline_sources.py # PIPELINE_LEAGUES, BETR_TO_DK_LEAGUE, DK/FD league slates
    │   ├── .env.example        # Betr Keycloak + optional BETR_JURISDICTION / header overrides; FD_*; DK_MARKETS_MAX_CONCURRENT
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
    │   │   ├── betr/           # betr_api (league CLI probe; status/isLive diagnostics), betr_auth, betr_engine, betr_orchestrator
    │   │   └── dabble_engine.py
    │   └── sportsbooks/
    │       ├── dk_engine.py
    │       ├── dk_api.py
    │       ├── dk_subcategory_discovery.py  # ad-hoc live/pregame subCategoryId scan helpers
    │       ├── fd_api.py       # league discovery; flatten; group_fd_line_rows
    │       └── fd_engine.py
    ├── parsers/
    │   ├── betr_parser.py
    │   ├── dk_parser.py
    │   ├── fd_parser.py        # grouped lines → line rows; league from parent prop
    │   └── normalize.py
    ├── core/
    │   ├── models.py
    │   ├── engine.py           # find_ev_opportunities; filter_min_ev; is_live; milestone row fields
    │   ├── line_adjustment.py  # O/U resolve; milestone de-vig + admission gate; multi-book consensus
    │   ├── flat_line.py
    │   ├── ev_pipeline.py
    │   ├── ev_display.py       # ranked table: Lg, Hit%, EV%, DK, FD, Src (ms🔶 milestone), Live
    │   ├── ev_run_diff.py      # consecutive top-N diff vs prior ev_opportunities.json
    │   ├── pipeline_scrape.py  # per-league dfs/books scrape orchestration
    │   ├── pipeline_artifacts.py
    │   ├── scrape_result.py
    │   ├── pipeline_timing.py  # wall-clock stage timer for --timing
    │   └── pipeline_runner.py  # --leagues, per-league --nba/--mlb/--wnba, --min-ev, --plus-ev-only, --timing
    ├── archive/dabble/
    ├── data/
    │   ├── raw/                # gitignored scrape inputs (.gitkeep only in repo)
    │   ├── processed/          # gitignored outputs (.gitkeep only in repo)
    │   └── archive/dabble/
    └── tests/
        ├── fixtures/
        └── unit/
```

**EV data flow:** `./ev` or `python -m core.pipeline_runner` → league loop (NBA, MLB, WNBA) × sources (dfs: betr; books: dk, fd) → in-memory merge → `normalize.py` (master + wrapped normalized + `unified_master_board.json`) → `ev_pipeline.py` (`load_comparison_inputs` / `run_ev_scan` honor `active_sources` on partial scrapes so stale off-run boards are not mixed in; `persist_match_diagnostics` with `by_league` → `match_report.json`; `run_id` check → `ev_opportunities.json` incl. `is_live` and milestone caveat fields; rotate + `ev_run_diff.json`) · `scrape_coverage.json` per run. Sharp resolution per Betr line: true O/U (DK/FD) preferred; `multi_book_consensus` when both exact; milestone (`N+`) gap-filler only when O/U missing or extrapolated — exact milestone overs admitted when hold-aware de-vig clears `MILESTONE_MIN_FAIR_OVER`. Partial book runs (e.g. `--books fd`) need DK **or** FD sharp props, not both. MLB: DK ingests pregame + in-progress events via `DK_MLB_LIVE_STAT_CATEGORIES` (8 batter tabs; per-market `None` would skip that tab — all set as of walks `9536`); Betr ingests scheduled + `IN_PROGRESS` from the same `getUpcomingEventsV2` call when `BETR_BASE_HEADERS` include app-parity client headers (`api_headers.py`). WNBA: pregame only; FD skipped.


## 6. Roadmap

### Open

* **Betr live fixture refresh:** Replace synthetic `tests/fixtures/betr_mlb_live.json` with a trimmed real DevTools capture (optional follow-up from [docs/plans/betr-live-events-feed.md](docs/plans/betr-live-events-feed.md)).
* **MLB props (pregame v2):** **Deferred:** `HITTER_STRIKEOUTS` (milestone-only on DK). Flat/push pitching K + milestone penalty — see [mlb.md](docs/betting_odds/mlb.md).
* **MLB milestone-only tabs (remaining):** `HITTER_STRIKEOUTS` (`17849`); pitching K push pairing (`15221` + `17323`) — parser/scrape gaps; general exact-milestone +EV admission is shipped (see Completed).
* **Additional sharp books:** Add a third sharp book (scrape → normalize → consensus); weights are env-tunable via `SHARP_BOOK_WEIGHTS_DK` / `SHARP_BOOK_WEIGHTS_FD` in `load_sharp_book_weights()`.
* **TheScore Bet (ESPN):** New sharp sportsbook — scrape → parse → normalize → multi-book consensus; mirror DK/FD layout in `scrapers/sportsbooks/`; platform doc in `docs/betting_odds/thescorebet.md`.
* **Granular promos / non-REGULAR Betr types:** Parse `MINI_BOOSTED`, `BOOSTED`, `EDGE`, etc.; store raw multipliers and alternate breakevens (wide-fetch fields already on master board).
* **Race-to-place parlay checker:** Build same parlay on DK/FD, compare to Betr promo multipliers (2-leg 3x→4x through 8-leg 100x→150x), hardcoded +EV threshold for take/pass.
* **`feat/fd-milestone-props`:** Ingest `TO_SCORE_*` / `TO_RECORD_*` / `N+_MADE_THREES` / double-double boards — master board + EV policy aligned with DK milestones (catalog in [fanduel.md](docs/betting_odds/fanduel.md)).

### Completed / archived

* Betr GraphQL scrape + parser + normalization pipeline (`betr_api.py`, wide `LeagueUpcomingEvents` fetch).
* Per-side Betr O/U EV: `allowedOptions` → parser side flags → `compare_betr_vs_draftkings` (under-only / over-only +EV when one side offered).
* DK markets API scrape via `dk_api.py` / `dk_engine.py` + `dk_parser.py` (httpx, no Playwright).
* **DK scrape hardening (Akamai 403):** per-event `fetch_event_all_markets`; `DK_MARKETS_MAX_CONCURRENT` semaphore (default 6); 403/429 retry/backoff; browser-like headers; league warm-up skipped on auto-discover — [docs/betting_odds/draftkings.md](docs/betting_odds/draftkings.md).
* `normalize.py` active platforms: Betr + DraftKings + FanDuel; Dabble archived.
* `ev_pipeline.py` loads `{betr,dk,fd}_normalized.json` (optional `active_sources` filter on partial scrapes) → `compare_betr_vs_draftkings` → `ev_opportunities.json`; ranked plays table via `ev_display.py`.
* Offline pytest suite: `tests/unit/test_{betr,dk,fd}_*`, `test_ev_engine`, `test_ev_pipeline`, `test_ev_display`, `test_line_adjustment`, `test_line_adjustment_multi_book`, `test_milestone_ev_board`, `test_pipeline_runner`, `test_normalize`, `test_math_utils`; fixtures incl. `betr_wnba_pregame.json`, `dk_milestone_ladder.json`, `fd_league_nba_events.json`, `fd_league_mlb_events.json`, `fd_event_*_player_{points,rebounds,assists}.json`, `fd_event_*_pitcher_props.json`.
* Betr breakeven aligned at **-120** across `math_utils`, parser side markers, and EV engine.
* Daily refresh orchestrator: `core/pipeline_runner.py` (`run_refresh`) — multi-league loop, `--dfs` / `--books` / `--leagues`, fresh-only runs with `run_id`, `core/pipeline_scrape.py`, `config/pipeline_sources.py`; repo-root `./ev` wrapper.
* Betr `--league` case normalization: `_normalize_betr_league` + `BetrEngine` uppercase GraphQL enum; GraphQL `errors` logged on invalid league — fixes empty MLB slate when invoking `./ev --league mlb`.
* Pipeline `--min-ev` / `--plus-ev-only`: filter ranked output to `ev > min_ev`; `plus_ev` flag on each row; default `min_ev=0` shows top-N including negative EV.
* Ranked plays table: `ev_display.py` — 11-column layout (Lg, widened Stat, Hit%, EV%, DK/FD O/U, Src, Live).
* FanDuel NBA event discovery: `fd_competitions.py`, `fd_api.fetch_league_event_ids`, `probe_fd_events`, `test_fd_event_discovery`.
* FanDuel event-page props + normalization: `fd_markets.py`, `fd_engine`, `fd_parser`, `test_fd_event_page`, `test_normalize_fd`.
* FanDuel core O/U default scrape: points / rebounds / assists via `FD_DEFAULT_SCRAPE_MARKETS` (`fd_engine` + `pipeline_runner`); multi-tab fixtures and tests.
* FanDuel extended O/U scrape + grouped master board: threes / combo stats via SGP tab; `group_fd_line_rows` + parser line expansion; `FD_EXTENDED_OU_MARKETS`.
* FanDuel market catalog in [docs/betting_odds/fanduel.md](docs/betting_odds/fanduel.md): default scrape table, skipped boards, tab/SGP fetch model, core-tab fixtures.
* FanDuel MLB pregame O/U: per-league `fd_markets` / `fd_competitions`; pitcher + batter tabs (`PITCHER_*` / `BATTER_*` marketTypes); `active_sources` in `ev_pipeline` / `pipeline_runner` for `--books fd` partial runs; `fd_parser` propagates `league` from grouped master-board parents; fixtures `fd_league_mlb_events.json`, `fd_event_35730475_pitcher_props.json`; `test_fd_markets`, MLB paths in `test_fd_engine` / `test_fd_api` / `test_normalize_fd` — [docs/plans/archive/fanduel-mlb-props.md](docs/plans/archive/fanduel-mlb-props.md).
* Multi-book consensus EV: `resolve_multi_book_sharp_quote`, `fd_exact` / `fd_alt` eligibility, `test_line_adjustment_multi_book`.
* EV run diff (consecutive `./ev`): `core/ev_run_diff.py` — rotate `ev_opportunities.json` → `ev_opportunities.previous.json`, compare top-N rows (`build_prop_key|side` buckets: new / removed / improved / fell), CLI summary after ranked table, `ev_run_diff.json`; `test_ev_run_diff.py`.
* Pipeline stage timing: `core/pipeline_timing.py` + `--timing` on `pipeline_runner` / `./ev` — wall-clock summary for scrape, normalize, and EV stages; `test_pipeline_timing.py`.
* Betr Keycloak auth probe: `python -m scrapers.dfs.betr.betr_auth` (`--try-grant`); refresh grant is the documented default — [docs/betting_odds/betr.md](docs/betting_odds/betr.md).
* Betr Keycloak `.env.example` defaults: public token URL (`account.betr.app/realms/betr/…`); `BETR_KEYCLOAK_CLIENT_ID=betr-rn` for fantasy.betr.app (refresh tokens client-bound; code default `betr-web` if unset).
* Multi-book consensus weights: `load_sharp_book_weights()` in `line_adjustment.py` — `SHARP_BOOK_WEIGHTS_DK` / `SHARP_BOOK_WEIGHTS_FD` env vars (default 1.0 each).
* **MLB live batter props (DK):** DK pregame+live event discovery; `DK_MLB_LIVE_STAT_CATEGORIES` + `configured_live_stat_categories_for_league` (8/8 live batter IDs incl. `walks` `9536`); `is_live` through DK parser → `ev_opportunities.json` + **Live** column in `ev_display` — [docs/plans/archive/mlb-live-props-dk.md](docs/plans/archive/mlb-live-props-dk.md).
* **Betr live MLB props (headers + engine):** App-parity GraphQL headers in `BETR_BASE_HEADERS` (`jurisdiction`, `channel`, `fantasy-api-version`, etc.) — same `LeagueUpcomingEvents` / `getUpcomingEventsV2` returns `IN_PROGRESS` + `isLive=true` (not a separate operation). `iter_live_events` / `extract_raw_props` merge scheduled + live; `betr_api` status/isLive probe; `is_live` through parser → EV — [docs/betting_odds/betr.md](docs/betting_odds/betr.md) (headers), [docs/plans/betr-live-events-feed.md](docs/plans/betr-live-events-feed.md) (resolved; fixture refresh optional).
* **DK live subCategoryId probe tooling:** `dk_subcategory_discovery.py`; `probe_dk_subcategories --league mlb --live --discover`; `probe_dk_discover --live` — live MLB tabs use different IDs than pregame ([mlb.md](docs/betting_odds/mlb.md)).
* **DK config rename (NBA):** `DK_NBA_*_STAT_CATEGORIES` / `DK_NBA_MILESTONE_STAT_CATEGORIES` / `DK_NBA_PENDING_STAT_CATEGORIES` (was generic `DK_STAT_CATEGORIES` names).
* **MLB pregame props (DK ship):** 13 markets Betr ↔ DK (`DK_MLB_STAT_CATEGORIES`, `MLB_ENABLED_MARKETS`, incl. `doubles`); FanDuel MLB wired later (see FanDuel MLB bullet above).
* **WNBA slate (Betr ↔ DK):** `PIPELINE_LEAGUES` + `BETR_TO_DK_LEAGUE["WNBA"]`; `DK_LEAGUE_SLATES["wnba"]` (`94682`/`4511`); explicit `DK_WNBA_*` stat aliases; per-league `--nba`/`--mlb`/`--wnba` shorthands (`merge_leagues_from_args`); `ev_display` **Lg** column; pregame only (FD auto-skipped); `betr_api` `__main__` forwards `[LEAGUE]` argv — [docs/plans/archive/wnba-betr-dk-slate.md](docs/plans/archive/wnba-betr-dk-slate.md).
* **Milestone +EV board admission:** Hold-aware milestone de-vig (`devig_milestone_fair_over`, `estimate_ou_hold`) and dynamic fair-over gate (`MILESTONE_MIN_FAIR_OVER`, `MILESTONE_ASSUMED_HOLD` in `settings.py`); only `dk_milestone_exact` on the board; JSON flags (`not_true_devig`, `milestone_devig_method`, `milestone_admitted`); CLI **Src** `ms🔶`; book-agnostic milestone ladder + `sharp_books` provenance — [docs/plans/archive/milestone-ev-board.md](docs/plans/archive/milestone-ev-board.md).
