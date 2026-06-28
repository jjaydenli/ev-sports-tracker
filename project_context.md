# Master Project Context: Multi-Platform EV Betting Engine


**Last verified:** 2026-06-27 (live MLB match gate — omit `event_hour` for `is_live` rows; DK live `event_start` can differ from Betr scheduled time)

## 1. Project Overview

+EV sports betting engine: compares fixed-payout player props on DFS apps (primarily **Betr**) against sharp sportsbook lines (**DraftKings**, **FanDuel**, **ESPN/TheScore Bet**). Standardizes naming, calculates no-vig fair value, outputs ranked JSON opportunities. **Dabble** archived under `backend/archive/dabble/`.


## 2. Tech Stack

- **Language:** Python async (`asyncio`, `httpx`)
- **DFS:** Betr GraphQL (`betr_api.py`, `betr_auth`)
- **Books:** DK REST (`dk_api.py`, `dk_engine.py`), FD REST (`fd_api.py`, `fd_engine.py`), ESPN GraphQL persisted-query (`espn_api.py`, `espn_auth.py`)
- **Headers:** `config/api_headers.py` (`BETR_*`, `DK_*`, `FD_*`, `ESPN_*`; Betr JWT via `settings.py`/`betr_auth`)
- **Logging:** `loguru` · **Testing:** `pytest`, `pytest-asyncio`, `pytest-mock` (offline fixtures only)
- *(Future: FastAPI, Redis, PostgreSQL, React)*

## 3. Platform-Specific Extraction Logic

Platform docs in [docs/betting_odds/](docs/betting_odds/). Each doc covers auth, scrape policy, markets, probes, and EV hooks.

### Betr (primary DFS)

- **Role:** Fixed-payout DFS props; primary DFS source.
- **Code:** `backend/scrapers/dfs/betr/` (`betr_api`, `betr_auth`, `betr_engine`, `betr_orchestrator`), `backend/parsers/betr_parser.py`
- **Live (MLB):** Same `LeagueUpcomingEvents` → `getUpcomingEventsV2` returns scheduled + `IN_PROGRESS` when headers match `picks.betr.app` DevTools (app-parity `jurisdiction`, `channel`, `fantasy-api-version` etc. in `BETR_BASE_HEADERS`). Engine merges via `extract_raw_props` / `iter_live_events` (`BETR_LIVE_EVENT_STATUSES`); live props require `marketStatus==OPENED` + `isLive==true`. `is_live`, `game` (e.g. `CIN@NYY`), `event_start` (UTC ISO) propagated through parser.
- **Probe:** `python -m scrapers.dfs.betr.betr_api [LEAGUE]` (default `NBA`; uppercase enum e.g. `MLB`; saves `data/processed/betr_league_upcoming_events_raw.json`)
- **Detail:** [docs/betting_odds/betr.md](docs/betting_odds/betr.md)

### DraftKings (sharp sportsbook)

- **Role:** Primary sharp O/U ladders + milestone (`N+`) fallbacks; primary input to `line_adjustment.py`.
- **Code:** `dk_engine.py`, `dk_api.py`, `dk_parser.py`, `config/dk_subcategories.py`, `scrapers/sportsbooks/dk_subcategory_discovery.py`
- **Milestones:** `line_kind=="milestone"` for NBA/WNBA/MLB `N+` boards. De-vig: contiguous ladder-normalization else hold-shrink (`estimate_ou_hold` / `MILESTONE_ASSUMED_HOLD`). Exact threshold only; post-de-vig fair over must clear `MILESTONE_MIN_FAIR_OVER`. Flagged `not_true_devig` / `milestone_devig_method`; CLI **Src** `ms🔶`. Logic is book-agnostic.
- **Live (MLB):** League slate discovers pregame (`NOT_STARTED`) + live (`IN_PROGRESS`/`STARTED`) events. Live scrapes `DK_MLB_LIVE_STAT_CATEGORIES` (8 batter tabs; live subcategoryIds differ from pregame, e.g. `walks` live `9536` vs pregame `17411`). Rows tagged `is_live`, `event_id`, `game`, `event_start` (DK `startEventDate` may differ from Betr/ESPN scheduled start once in-play).
- **Config:** `dk_subcategories.py` — `DK_NBA_*` / `DK_WNBA_*` / `DK_MLB_STAT_CATEGORIES` / `DK_MLB_LIVE_STAT_CATEGORIES`
- **Detail:** [docs/betting_odds/draftkings.md](docs/betting_odds/draftkings.md)

### FanDuel (sharp sportsbook)

- **Role:** Second sharp book. **NBA** (per-stat tabs + SGP extended O/U). **MLB** pregame O/U + milestones. **Pregame only — no live FD MLB.**
- **Code:** `fd_api.py`, `fd_engine.py`, `fd_parser.py`, `config/fd_markets.py`, `config/fd_competitions.py`, `scripts/probe_fd_events.py`
- **MLB O/U:** `FD_LEAGUE_SLATES["mlb"]`; pitcher-props + batter-props tabs (`PITCHER_*` / `BATTER_*` marketTypes); 13-market scrape via per-league `fd_markets` / `fd_competitions` dispatch.
- **MLB milestones:** `TO_RECORD_*` / `PLAYER_TO_RECORD_*` one-sided over boards. `flatten_player_milestone_market` in `fd_api.py`; `FD_MILESTONE_MARKETS_BY_LEAGUE["mlb"]` (hits, total bases, runs, RBI, H+R+RBI). `group_fd_line_rows` / `merge_prop_rows` key by `line_kind`; true O/U wins over milestone in `resolve_sharp_quote`.
- **Event start + game:** `build_event_start_map` / `build_event_game_map` in `fd_competitions.py`; `fd_engine._fetch_league_slate` returns `(event_ids, start_map, game_map)`. `fd_parser` propagates `league`, `event_start`, `game`, `milestone_threshold`.
- **Detail:** [docs/betting_odds/fanduel.md](docs/betting_odds/fanduel.md)

### ESPN / TheScore Bet (sharp sportsbook)

- **Role:** Third sharp book (`espn` source token). API is **GraphQL persisted queries (GET) behind an anonymous JWE** (validated live 2026-06-22, app `26.12.0`) — not REST.
- **Code:** `espn_api.py` (client + drawer flatten), `espn_auth.py` (Startup JWE mint + cache), `espn_engine.py`, `espn_parser.py`, `config/espn_queries.py` (hashes), `config/espn_markets.py`, `config/espn_competitions.py`
- **MLB:** Pregame + **live (IN_PLAY)** O/U via per-event pitcher-props/batter-props drawers. OPEN-only status guard at market + selection level. Live tagged `is_live=True`. **Milestones:** batter `N+` boards (singles, doubles, runs, stolen_bases) via LIST-type drawer labelText dispatch; `N+` → `N−0.5` line; hold-shrink de-vig. **WNBA** registered in `ESPN_LEAGUE_SLATES` (capture pending). NBA deferred.
- **Consensus:** `SHARP_BOOK_WEIGHTS_ESPN` in `load_sharp_book_weights()`; N-book weighted de-vig when 2+ books have exact O/U.
- **Detail:** [docs/betting_odds/espn.md](docs/betting_odds/espn.md)

### Dabble (archived)

`backend/archive/dabble/` · [docs/betting_odds/dabble.md](docs/betting_odds/dabble.md) · mobile-only Proxyman notes: [docs/proxyman_dabble_setup.md](docs/proxyman_dabble_setup.md)

### MLB

13-market pregame O/U (`DK_MLB_STAT_CATEGORIES`, incl. `doubles`) + live batter O/U (`DK_MLB_LIVE_STAT_CATEGORIES`, 8 tabs). FD pregame O/U (13 markets, pitcher + batter tabs) + milestone `N+` boards. ESPN pregame + live O/U + batter milestone `N+` boards (singles, doubles, runs, stolen_bases). Betr: scheduled + `IN_PROGRESS` via app-parity `BETR_BASE_HEADERS`. CLI: `./ev --mlb` or `./ev --leagues mlb`.

**Cross-book matching:** `build_match_context_key` = `player|market|league|[event_hour]|[live]`; `event_hour` = UTC hour-floor (`iso[:13]`) — sole **pregame** game discriminator; `game` AWAY@HOME is display-only. **Live** rows (`is_live`) omit `event_hour` (Betr scheduled vs DK actual-start timestamps can diverge by >1h); `|live` suffix scopes the snapshot. Pregame Betr without `event_start` fails closed (no match). Doubleheaders/series separated by `event_hour` for pregame only (minute drift within same hour still matches).

**o0.5 equivalence:** At line `0.5`, `_filter_sharp_props_by_match_context` (`engine.py`) may borrow `hits`/`total_bases` cross-market per book when native o0.5 missing (`O05_EQUIVALENT_MARKETS` in `market_maps.py`); relabeled shallow copy, milestone rows excluded, bidirectional.

### WNBA

Pregame only — Betr (`League!="WNBA"`) vs DK (`DK_LEAGUE_SLATES["wnba"]`, `DK_WNBA_*` stat aliases). FD auto-skipped (no `FD_LEAGUE_SLATES` entry). CLI: `./ev --wnba`. Betr probe: `python -m scrapers.dfs.betr.betr_api WNBA`.

## 4. Quantitative Modeling & Math

- **Cross-book display vs matching:** `game` (AWAY@HOME) populated for UI only. `config/team_abbrev.py`: `TEAM_ABBR_ALIASES` / `canonicalize_team_abbr` for DK/ESPN; `game_key_from_full_names` for FD. Missing/mismatched `game` blanks display only — match gate never reads it.
- **Match keys:** `build_match_context_key` → `player|market|league|[event_hour]|[live]`; `build_player_market_key` → `player|market|[event_hour]|[live]`. Pregame: `event_hour` when `event_start` present. Live: omit `event_hour` (only `|live` suffix); pregame without `event_start` also omits hour. **Ambiguous collision:** same key+line with conflicting odds drops the `pm_key` (instead of last-write-wins).
- **Market mapping:** `PLATFORM_MARKET_MAPPINGS` → `MARKETS` in `config/market_maps.py`.
- **De-vig (O/U):** DK/FD American odds → implied probabilities; **multiplicative** removal in `utils/math_utils.py`.
- **De-vig (milestone):** `devig_milestone_fair_over` in `line_adjustment.py` — contiguous ladder-normalization else hold-shrink (`estimate_ou_hold` / `MILESTONE_ASSUMED_HOLD`); gate `MILESTONE_MIN_FAIR_OVER` (env-tunable in `settings.py`).
- **EV resolution:** Per book: `resolve_book_sharp_quote` prefers O/U (DK: exact/alt/interpolated; FD: exact/alt only) else milestone (exact threshold, hold-gate must clear). Multi-book: `multi_book_consensus` when 2+ books have exact O/U (N-book weighted de-vig via `SHARP_BOOK_WEIGHTS_*`); cross-book O/U+milestone combo keeps milestone display-only (`ou_ms_combo`, Src `ou+ms🔶`). One EV row per Betr side. `filter_min_ev` / `--plus-ev-only` / `--min-ev`. Default breakeven `BETR_STANDARD_BREAKEVEN_ODDS` (-120).

## 5. Architecture & File Structure

```text
ev-sports-tracker/
│   ├── rules/                  # path-scoped: backend/**, docs/plans/**
│   └── skills/
│       ├── design-handoff/     # plan-file workflow → docs/plans/
├── docs/
│   ├── plans/                  # active handoffs (_template.md, _example.md); archive/ for shipped specs
├── scripts/
│   ├── archive_plan.sh         # move shipped handoff → docs/plans/archive/ (+ link rewrites)
│   ├── check_plan_archived.sh  # pre-PR / CI guard — fails shipping PRs with active handoffs
│   └── open_pr.sh              # PR title/body + push; calls check before create/push
├── .github/workflows/ci.yml    # PR: check_plan_archived.sh then backend pytest -q
├── ev                          # bash wrapper → backend pipeline_runner (same flags)
└── backend/
    ├── config/
    │   ├── api_headers.py      # BETR_BASE_HEADERS (jurisdiction/channel/fantasy-api-version); DK_*; FD_*; ESPN_*
    │   ├── market_maps.py      # PLATFORM_MARKET_MAPPINGS; O05_EQUIVALENT_MARKETS (hits ↔ total_bases at 0.5)
    │   ├── team_abbrev.py      # TEAM_ABBR_ALIASES + canonicalize_team_abbr (DK/ESPN display); game_key_from_full_names (FD)
    │   ├── settings.py         # SHARP_BOOK_WEIGHTS_*; MILESTONE_MIN_FAIR_OVER / MILESTONE_ASSUMED_HOLD
    │   ├── dk_subcategories.py # DK_NBA_* / DK_WNBA_* / DK_MLB_* STAT_CATEGORIES; DK_MLB_LIVE_STAT_CATEGORIES
    │   ├── dk_discovery.py     # ID scan ranges; DK_MLB_LIVE_DISCOVERY_ID_RANGES; discovery output paths
    │   ├── discovery/          # per-league progress manifests (mlb.yaml)
    │   ├── fd_competitions.py  # FD_LEAGUE_SLATES; extract_event_ids; build_event_start_map; build_event_game_map
    │   ├── fd_markets.py       # per-league tab/market dispatch; NBA + MLB O/U + MLB milestone marketType parse
    │   ├── espn_queries.py     # GraphQL persisted-query hashes + extensions + app version
    │   ├── espn_competitions.py # ESPN_LEAGUE_SLATES (canonicalUrl + Lines section id); GraphQL payload traversal
    │   ├── espn_markets.py     # O/U drawer groupId → canonical market; milestone labelText → market
    │   ├── pipeline_sources.py # PIPELINE_LEAGUES, BOOK_SOURCES (dk, fd, espn), BOOK_TO_PLATFORM
    │   ├── .env.example        # Betr Keycloak + optional header overrides; FD_*; ESPN_*; DK_MARKETS_MAX_CONCURRENT
    │   └── .env                # local secrets (gitignored)
    ├── scripts/
    │   ├── probe_dk_discover.py
    │   ├── probe_dk_subcategories.py
    │   ├── probe_fd_events.py
    │   ├── probe_espn_events.py
    │   └── probe_espn_milestone_drawers.py
    ├── utils/
    │   ├── math_utils.py
    │   └── formatting.py
    ├── scrapers/
    │   ├── base_scraper.py
    │   ├── dfs/
    │   │   ├── betr/           # betr_api (league CLI probe; status/isLive diagnostics), betr_auth, betr_engine, betr_orchestrator
    │   │   └── dabble_engine.py
    │   └── sportsbooks/
    │       ├── dk_engine.py    # tags is_live, event_id, game, event_start per slate row
    │       ├── dk_api.py       # game_key_from_dk_event; build_event_game_map; build_event_start_map
    │       ├── dk_subcategory_discovery.py  # ad-hoc live/pregame subCategoryId scan helpers
    │       ├── fd_api.py       # league discovery; flatten O/U + MLB milestones; group_fd_line_rows (line_kind key)
    │       ├── fd_engine.py    # _fetch_league_slate (single fetch); tags event_start + game on rows
    │       ├── espn_api.py     # GraphQL client (ESPNGraphQLClient, 401-remint) + O/U + milestone drawer flatten (OPEN-only status guard)
    │       ├── espn_auth.py    # ensure_espn_token: Startup JWE mint + (install_id, token) cache
    │       └── espn_engine.py  # read-chain: games (PRE_GAME+IN_PLAY) → prop sections → O/U + milestone drawers → flatten; tags game, event_start, is_live
    ├── parsers/
    │   ├── betr_parser.py      # propagates game, is_live, event_start
    │   ├── dk_parser.py        # propagates event_id, game, event_start, is_live
    │   ├── fd_parser.py        # grouped lines → line rows; league, event_start, game, milestone_threshold from parent
    │   ├── espn_parser.py      # propagates event_id, game, event_start, is_live
    │   └── normalize.py
    ├── core/
    │   ├── models.py
    │   ├── engine.py           # find_ev_opportunities; per-Betr match-context filter (+ o0.5 hits/tb borrow); filter_min_ev
    │   ├── line_adjustment.py  # build_match_context_key (pregame event_hour; live omits hour); build_player_market_key; collision drop; O/U + milestone de-vig; multi-book consensus
    │   ├── flat_line.py
    │   ├── ev_pipeline.py
    │   ├── ev_display.py       # ranked table: Lg, Game, Hit%, EV%, DK, FD, ESPN, Src (ms🔶), Live
    │   ├── ev_run_diff.py      # consecutive top-N diff vs prior ev_opportunities.json
    │   ├── pipeline_scrape.py  # per-league dfs/books scrape orchestration
    │   ├── pipeline_artifacts.py
    │   ├── scrape_result.py
    │   ├── pipeline_timing.py  # wall-clock stage timer for --timing
    │   └── pipeline_runner.py  # --leagues, --nba/--mlb/--wnba, --books, --min-ev, --plus-ev-only, --timing
    ├── archive/dabble/
    ├── data/
    │   ├── raw/                # gitignored scrape inputs (.gitkeep only)
    │   ├── processed/          # gitignored outputs (.gitkeep only)
    │   └── archive/dabble/
    └── tests/
        ├── conftest.py
        ├── fixtures/
        ├── integration/
        └── unit/               # golden snapshots, property (test_math_properties), fixture-shape, match-stats coverage; 544 tests
```

**EV data flow:** `./ev` → league loop (NBA, MLB, WNBA) × sources (betr; dk, fd, espn) → `normalize.py` (master board + `unified_master_board.json`; rows carry `event_start` UTC ISO + display `game`) → `ev_pipeline.py` (`load_comparison_inputs` / `run_ev_scan` honor `active_sources` for partial book runs; `persist_match_diagnostics`; emits `ev_opportunities.json`, `ev_run_diff.json`, `scrape_coverage.json`). Sharp resolution per Betr line: `_filter_sharp_props_by_match_context` (match-context key filter — pregame by `event_hour`, live by `|live` only + per-book o0.5 borrow) → per-book `resolve_book_sharp_quote` → `resolve_multi_book_sharp_quote` → one EV row with per-book odds columns.


## 6. Roadmap

### Next up (sequenced — live-first, then breadth)

1. ~~**Live MLB — ESPN**~~ ✅ **Implemented** — OPEN-only status guard in `flatten_drawer_content`; `_resolve_games` filters to `{PRE_GAME, IN_PLAY}`; `is_live=True` in `espn_engine` + `espn_parser`; declared in `NormalizedProp`.
2. ~~**Live MLB — DK/Betr match gate**~~ ✅ **Implemented** — `build_match_context_key` / `build_player_market_key` omit `event_hour` for `is_live` rows so DK live `startEventDate` (actual start) can match Betr scheduled `event_start`.
3. **Live MLB — FanDuel:** Flip the deliberate in-play skip (`scrapers/sportsbooks/fd_api.py:439-440`; `event_page_in_play` `:418-422` already reads `inPlay`) into handling; emit `is_live=True` rows; confirm event-page tabs return live ladders. User-owned: confirm an in-play FD tab fetch returns live ladders.
4. **New sharp book — Caesars (breadth):** Live MLB props — new `*_api`/`*_engine`/`*_parser` trio + `config/` competitions/markets + `team_abbrev.py` canon + `pipeline_sources.py`. Mirror DK/FD/ESPN layout.

### Open

- **Betr live fixture refresh:** Replace synthetic `tests/fixtures/betr_mlb_live.json` with a real DevTools capture.
- **MLB props (pregame v2):** `HITTER_STRIKEOUTS` (milestone-only on DK); flat/push pitching K + milestone penalty — see [mlb.md](docs/betting_odds/mlb.md).
- **MLB milestone-only tabs (remaining):** `HITTER_STRIKEOUTS` (`17849`); pitching K push pairing (`15221` + `17323`).
- **Additional sharp books:** Extend weighted consensus beyond DK/FD/ESPN (`SHARP_BOOK_WEIGHTS_*`).
- **Granular promos / non-REGULAR Betr types:** Parse `MINI_BOOSTED`, `BOOSTED`, `EDGE`, etc.; store raw multipliers and alternate breakevens.
- **Race-to-place parlay checker:** Build same parlay on DK/FD, compare to Betr promo multipliers (2-leg 3x→4x through 8-leg 100x→150x).
- **Open-parlay live checker (`./check`):** Scan Betr account for open/pending parlays, cross-reference vs current live odds. Needs authenticated bet-history access.
- **Promo prop scanner (`./promos`):** Find Betr promo props; back out per-prop multiplier via 2-leg parlay construction.
- **FanDuel two-sided MLB milestones:** If live captures show Yes/No runners, ingest as true O/U at line `N-0.5`.
- **FanDuel NBA/WNBA milestones:** `TO_SCORE_*` / made-threes / double-double (deferred from [docs/plans/archive/fd-milestone-props.md](docs/plans/archive/fd-milestone-props.md)).
- **Same-name player disambiguation:** Use book player IDs / team context to split collisions instead of key-drop.
- **FanDuel 1+ hit milestone → o0.5 total_bases:** Map FD one-sided hit milestones as an o0.5 total_bases source.
