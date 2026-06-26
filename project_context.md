# Master Project Context: Multi-Platform EV Betting Engine


**Last verified:** 2026-06-26 (engine regression safety net — golden/coverage/property tests; event-hour match gate; ambiguous sharp-ladder collision drop)

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
* **Live (MLB runs):** Same `LeagueUpcomingEvents` → `getUpcomingEventsV2` operation returns scheduled + `IN_PROGRESS` when client headers match `picks.betr.app` DevTools (without `jurisdiction` / `channel` / fantasy API versions the API may return pregame-only). Engine merges via `extract_raw_props` / `iter_live_events` (`BETR_LIVE_EVENT_STATUSES`); live projections require `marketStatus == OPENED` and `isLive == true`; master board and parser propagate `is_live`, `game` (matchup key e.g. `CIN@NYY` from event `name`), and `event_start` (UTC ISO from event `date`). `BetrEngine.scrape` logs scheduled/live counts and warns when zero live events during a live slate.

### DraftKings (sharp sportsbook)

* **Role:** Sharp O/U ladders and milestone (`N+`) fallbacks; primary input to `line_adjustment.py`.
* **Milestones:** DK emits `line_kind == "milestone"` for NBA/WNBA/MLB `N+` boards; FanDuel emits MLB milestones only (`TO_RECORD_*` / `PLAYER_TO_RECORD_*` on pitcher/batter tabs — see FanDuel below). Exact milestone overs at the Betr line (`dk_milestone_exact` / `fd_milestone_exact`) can reach the +EV board when hold-aware de-vig clears `MILESTONE_MIN_FAIR_OVER` (default −160 fair over); interpolated/extrapolated milestones stay off the board. De-vig: contiguous `N+` ladder normalization, else hold-shrink from sibling O/U hold (`estimate_ou_hold`) or `MILESTONE_ASSUMED_HOLD`. Admitted rows flagged `not_true_devig` / `milestone_devig_method` in JSON; CLI **Src** shows `ms🔶`. Logic is book-agnostic (milestone ladder = union of sharp-book milestone props; `sharp_books` = source book).
* **Code:** `dk_engine.py`, `dk_api.py`, `dk_parser.py`, `config/dk_subcategories.py`, `scrapers/sportsbooks/dk_subcategory_discovery.py`
* **Detail:** [docs/betting_odds/draftkings.md](docs/betting_odds/draftkings.md) — slates, subcategories, eligible `line_source` values.
* **Config:** `DK_NBA_*_STAT_CATEGORIES` (NBA O/U + milestones); `DK_WNBA_*` aliases same prop IDs with slate `94682` / `4511`; `DK_MLB_STAT_CATEGORIES` / `DK_MLB_LIVE_STAT_CATEGORIES` (MLB pregame + live batter tabs via `stat_categories_for_league` / `live_stat_categories_for_league`).
* **Live (MLB):** League slate discovers pregame (`NOT_STARTED`) and live (`IN_PROGRESS`, `STARTED` in `LIVE_EVENT_STATUSES`) events; live events scrape `configured_live_stat_categories_for_league` (`DK_MLB_LIVE_STAT_CATEGORIES` — full 8-market batter O/U set incl. `walks` live `9536` vs pregame `17411`). Live subCategoryIds often differ from pregame (probe: `probe_dk_subcategories <live_event_id> --league mlb --live --discover`). Unset live IDs skip that market on in-game events. DK rows tagged `is_live`, `event_id`, display `game` (`build_event_game_map` / `game_key_from_dk_event` in `dk_api.py` — AWAY@HOME from participant `shortName`), and `event_start` (`build_event_start_map` — UTC ISO from `startEventDate`); `dk_parser` propagates all four.

### FanDuel (sharp sportsbook)

* **Role:** Second sharp book; multi-book consensus when DK+FD align at the Betr line. **NBA** (per-stat tabs + SGP extended O/U). **MLB** pregame O/U (`FD_LEAGUE_SLATES["mlb"]`; `pitcher-props` / `batter-props` tabs — `PITCHER_*` / `BATTER_*` `TOTAL_*` marketTypes; 13-market scrape via per-league `fd_markets` / `fd_competitions` dispatch). Pregame only — no live FD MLB scrape.
* **MLB milestones:** `fd_api.flatten_player_milestone_market` ingests one-sided `TO_RECORD_*` / `PLAYER_TO_RECORD_*` boards on the same MLB tabs (`parse_player_milestone_market_type` in `fd_markets.py`; `FD_MILESTONE_MARKETS_BY_LEAGUE["mlb"]` — hits, total bases, runs, RBI, H+R+RBI). Rows mirror DK shape: `line_kind == "milestone"`, `milestone_threshold=N`, `line=N-0.5`, over-only `over_odds`, `under_odds=None`. `group_fd_line_rows` / `merge_prop_rows` key by `line_kind` so O/U and milestone ladders for the same player|market stay separate. True FD O/U still wins over FD milestone in `resolve_sharp_quote`. NBA `TO_SCORE_*` / made-threes / double-double boards remain skipped (deferred).
* **Parser:** `fd_parser.py` expands grouped `lines` ladders to line-level `fd_normalized.json` rows; copies `league`, `event_start`, and `game` from the grouped master-board parent (set in `fd_engine`) so `build_prop_key` can match Betr/DK by league and `find_ev_opportunities` can gate on UTC event-hour; propagates `milestone_threshold` on milestone lines. Pregame only — no `is_live`; live Betr rows do not match pregame FD milestone/O/U via the `|live` ladder suffix (see §4).
* **Code:** `fd_api.py`, `fd_engine.py`, `fd_parser.py`, `config/fd_markets.py`, `config/fd_competitions.py`, `scripts/probe_fd_events.py`
* **Event start + game:** `build_event_start_map` and `build_event_game_map` in `fd_competitions.py` map event_id → UTC `openDate` and canonical `AWAY@HOME` (full team names via `config.team_abbrev.game_key_from_full_names`). `fd_engine._fetch_league_slate` calls `fetch_league_events` once and returns `(event_ids, start_map, game_map)`; props tagged `event_start` and `game` (display) before master-board write.
* **Detail:** [docs/betting_odds/fanduel.md](docs/betting_odds/fanduel.md) — event discovery, tabs, O/U vs milestones.

### ESPN / TheScore Bet (sharp sportsbook)

* **Role:** Third sharp book (`espn` source token). API is **GraphQL persisted queries (GET) behind an anonymous JWE** (validated live 2026-06-22, app `26.12.0`) — not FD/DK REST. **MLB** O/U first (pregame; per-event `pitcher-props`/`batter-props` O/U drawers); **WNBA** registered in `ESPN_LEAGUE_SLATES` pending its own capture. NBA deferred. O/U only — no milestones in v1.
* **Code:** `espn_api.py` (persisted-query client + drawer flatten), `espn_auth.py` (Startup JWE mint + cache), `espn_engine.py`, `espn_parser.py`, `config/espn_queries.py` (hashes), `config/espn_markets.py`, `config/espn_competitions.py` (`extract_games` + canonical display `game` via `team_abbrev`), `scripts/probe_espn_events.py`
* **Detail:** [docs/betting_odds/espn.md](docs/betting_odds/espn.md) — GraphQL transport, read chain, auth, O/U leaf shape.
* **Consensus:** `load_sharp_book_weights()` includes `SHARP_BOOK_WEIGHTS_ESPN`; `_consensus_sharp_quote` N-book weighted de-vig when 2+ books have exact O/U at the Betr line; ESPN exact-only (`espn_exact` / `espn_alt`).

### Dabble (archived)

* **Code:** `backend/archive/dabble/` · **Detail:** [docs/betting_odds/dabble.md](docs/betting_odds/dabble.md) · mobile-only capture: [docs/proxyman_dabble_setup.md](docs/proxyman_dabble_setup.md)

### MLB

* **Detail:** [docs/betting_odds/mlb.md](docs/betting_odds/mlb.md) — pregame 13-market O/U slate (`DK_MLB_STAT_CATEGORIES`, incl. `doubles`) plus live batter O/U (`DK_MLB_LIVE_STAT_CATEGORIES` — all 8 batter live IDs set, e.g. `walks` `9536` live vs `17411` pregame; live IDs differ from pregame on many tabs). FanDuel MLB: same 13-market pregame O/U list (pitcher + batter tabs) plus milestone `N+` boards on those tabs (hits, total bases, runs, RBI, H+R+RBI); `./ev --mlb --books fd` or full `--mlb` Betr ↔ (DK + FD + ESPN) consensus and milestone gap-fill. EV output rows include `is_live` (ranked table **Live** column). **Cross-book matching:** `find_ev_opportunities` filters DK/FD/ESPN props per Betr row via `build_match_context_key` (`player|market|league|[event_hour]|[live]` in `line_adjustment.py`; `event_hour = iso[:13]` is the sole game discriminator — `game` AWAY@HOME is display-only) before building sharp ladders — live Betr props still require `|live` suffix; pregame Betr without `event_start` fails closed; doubleheaders and series games separated by `event_hour` (minute drift within the same hour still matches; abbreviation vocabulary mismatches no longer block matches). **o0.5 hits ↔ total_bases:** at line `0.5` only, `_filter_sharp_props_by_match_context` (`engine.py`) may borrow the other market's o/u row from the same sharp book when that book lacks a native o0.5 for the Betr market — shallow copy with `market` relabeled so downstream ladder/EV logic is unchanged; prefer native per book; milestone rows excluded; bidirectional (`hits` ↔ `total_bases`); `O05_EQUIVALENT_MARKETS` in `market_maps.py`. No CLI flag — DK and Betr live discovery are standing behavior on `./ev --leagues mlb` (Betr: app-parity GraphQL headers; DK: `DK_MLB_LIVE_STAT_CATEGORIES`).

### WNBA

* **Detail:** Pregame only — Betr wide fetch (`League!` = `WNBA`) vs DK sharp (`DK_LEAGUE_SLATES["wnba"]`, NBA-parity O/U + milestone fallback IDs via `DK_WNBA_*`). FanDuel auto-skipped (no `FD_LEAGUE_SLATES` entry). CLI: `./ev --wnba` or `--leagues wnba`. Betr probe: `python -m scrapers.dfs.betr.betr_api WNBA`.

## 4. Quantitative Modeling & Math

* **Cross-book display vs matching:** `game` (`AWAY@HOME`) is populated on props for UI (`ev_display` **Game** column) via each book's slate walk (`build_event_game_map` in `dk_api.py` / `fd_competitions.py`; ESPN `_event_game_key` in `espn_competitions.py`). `config/team_abbrev.py` canonicalizes deviating abbreviation codes (DK/ESPN → betr vocabulary via `TEAM_ABBR_ALIASES` / `canonicalize_team_abbr`) and resolves FanDuel full team names (`game_key_from_full_names`). Missing or mismatched `game` blanks display only — the match gate never reads it.
* **Match keys:** `build_match_context_key` → `player|market|league|[event_hour]|[live]`; `build_player_market_key` → `player|market|[event_hour]|[live]`. `event_hour` is UTC hour-floor (`iso[:13]`) from `event_start` and is the sole game discriminator (doubleheaders 3+ hours apart stay distinct). Live rows without `event_start` omit the hour segment and fall back to `player|market|[league]|live`. **Ambiguous ladder collisions:** when two sharp rows share the same key and line but carry *conflicting* odds (typical same-name player clash), `build_player_market_ladder` / milestone ladder builders drop that `pm_key` from matching with a warning instead of silently overwriting.
* **Market mapping:** Platform names normalized via `PLATFORM_MARKET_MAPPINGS` → `MARKETS` in `config/market_maps.py`.
* **De-vigging:** O/U — DK/FD American odds → implied probabilities; **multiplicative** vig removal in `utils/math_utils.py`. Milestone (`N+`, over-only) — `devig_milestone_fair_over` in `line_adjustment.py`: ladder-normalization on contiguous thresholds, else hold-shrink using observed O/U hold (`estimate_ou_hold`) or `MILESTONE_ASSUMED_HOLD`; admission floor `MILESTONE_MIN_FAIR_OVER` (env-tunable in `settings.py`).
* **EV calculation:** `find_ev_opportunities` / `compare_betr_vs_draftkings` in `core/engine.py` — for each Betr prop, `_filter_sharp_props_by_match_context` keeps DK/FD/ESPN rows where `build_match_context_key` matches (`player|market|league|[event_hour]|[live]`; hour-floor `iso[:13]`; pregame without Betr `event_start` skipped fail-closed; live without `event_start` matches on `player|market|[league]|live` only). Filtered props feed per-book sharp resolution in `line_adjustment.py` (`resolve_book_sharp_quote` / `resolve_multi_book_sharp_quote`): ladders indexed by `build_player_market_key` (`player|market`, optional `|event_hour`, optional `|live`; ambiguous same-line odds collisions drop the key). Ladder rows carry `event_start`; `ResolvedSharpQuote.sharp_event_start` records provenance. Each book independently prefers O/U (DK: exact/alt/interpolated; FD: exact/alt only), else milestone when O/U missing or DK-extrapolated only; **one EV row per Betr side** with DK/FD column odds composed from each book. EV from `multi_book_consensus` when both exact O/U, else best eligible O/U (DK preferred), else admitted exact milestone; cross-book milestone is display-only when the other book supplies O/U (`line_source` `ou_ms_combo` → Src `ou+ms🔶`; milestone one-sided columns `{over}/🔶`). Eligible O/U: multiplicative de-vig. Eligible milestone: exact threshold only, post-de-vig fair over must clear gate. Each row gets `plus_ev` when `ev > min_ev`. Optional `filter_min_ev` drops sub-threshold rows before `top_n` (pipeline: auto when `--min-ev > 0`, or `--plus-ev-only` with any `--min-ev`). `run_ev_scan` logs a ranked plays table (`core/ev_display.py`: Lg, Hit%, EV%, DK/FD O/U, `line_source` — compact widths; milestone exact → `ms🔶`) plus run-over-run diff (`core/ev_run_diff.py`: new / removed / improved / fell vs prior top-N). JSON output capped at `top_n` (default 15). Milestone rows carry `milestone_admitted`, `milestone_devig_method`, `not_true_devig`, and vig caveats. Default DFS breakeven: `BETR_STANDARD_BREAKEVEN_ODDS` (-120); flat integer Betr lines optional (`--include-flat-lines`).

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
├── ev                            # bash wrapper → backend pipeline_runner (same flags)
└── backend/
    ├── config/
    │   ├── api_headers.py      # BETR_BASE_HEADERS (jurisdiction/channel/fantasy-api-version); DK_*; FD_*; ESPN_*
    │   ├── market_maps.py      # PLATFORM_MARKET_MAPPINGS; O05_EQUIVALENT_MARKETS (hits ↔ total_bases at 0.5)
    │   ├── team_abbrev.py    # TEAM_ABBR_ALIASES + canonicalize_team_abbr (DK/ESPN display); game_key_from_full_names (FD)
    │   ├── settings.py           # SHARP_BOOK_WEIGHTS_*; MILESTONE_MIN_FAIR_OVER / MILESTONE_ASSUMED_HOLD
    │   ├── dk_subcategories.py   # DK_NBA_* / DK_WNBA_* / DK_MLB_* STAT_CATEGORIES; DK_MLB_LIVE_STAT_CATEGORIES
    │   ├── dk_discovery.py       # ID scan ranges; DK_MLB_LIVE_DISCOVERY_ID_RANGES; discovery output paths
    │   ├── discovery/          # per-league progress manifests (mlb.yaml)
    │   ├── fd_competitions.py  # FD_LEAGUE_SLATES; extract_event_ids; build_event_start_map; build_event_game_map (display)
    │   ├── fd_markets.py       # per-league tab/market dispatch; NBA + MLB O/U + MLB milestone marketType parse
    │   ├── espn_queries.py     # GraphQL persisted-query hashes + extensions + app version
    │   ├── espn_competitions.py  # ESPN_LEAGUE_SLATES (canonicalUrl + Lines section id); GraphQL payload traversal (games/sections/drawers)
    │   ├── espn_markets.py     # O/U drawer groupId → canonical market dispatch
    │   ├── pipeline_sources.py # PIPELINE_LEAGUES, BOOK_SOURCES (dk, fd, espn), BOOK_TO_PLATFORM
    │   ├── .env.example        # Betr Keycloak + optional header overrides; FD_*; ESPN_*; DK_MARKETS_MAX_CONCURRENT
    │   └── .env                # local secrets (gitignored)
    ├── scripts/
    │   ├── probe_dk_discover.py
    │   ├── probe_dk_subcategories.py
    │   ├── probe_fd_events.py
    │   └── probe_espn_events.py
    ├── utils/
    │   ├── math_utils.py
    │   └── formatting.py
    ├── scrapers/
    │   ├── base_scraper.py
    │   ├── dfs/
    │   │   ├── betr/           # betr_api (league CLI probe; status/isLive diagnostics), betr_auth, betr_engine, betr_orchestrator
    │   │   └── dabble_engine.py
    │   └── sportsbooks/
    │       ├── dk_engine.py      # tags is_live, event_id, game, event_start per slate row
    │       ├── dk_api.py         # game_key_from_dk_event; build_event_game_map (display); build_event_start_map
    │       ├── dk_subcategory_discovery.py  # ad-hoc live/pregame subCategoryId scan helpers
    │       ├── fd_api.py       # league discovery; flatten O/U + MLB milestones; group_fd_line_rows (line_kind key)
    │       ├── fd_engine.py      # _fetch_league_slate (single slate fetch); tags event_start + game on rows
    │       ├── espn_api.py     # GraphQL persisted-query client (ESPNGraphQLClient, 401-remint) + O/U drawer flatten
    │       ├── espn_auth.py    # ensure_espn_token: Startup JWE mint + (install_id, token) cache
    │       └── espn_engine.py  # read-chain walk: games → prop sections → O/U drawers → flatten; tags game + event_start
    ├── parsers/
    │   ├── betr_parser.py        # propagates game, is_live, event_start
    │   ├── dk_parser.py          # propagates event_id, game, event_start, is_live
    │   ├── fd_parser.py        # grouped lines → line rows; league, event_start, game, milestone_threshold from parent
    │   ├── espn_parser.py
    │   └── normalize.py
    ├── core/
    │   ├── models.py
    │   ├── engine.py           # find_ev_opportunities; per-Betr match-context filter (+ o0.5 hits/tb borrow); filter_min_ev; milestone row fields
    │   ├── line_adjustment.py  # build_match_context_key; build_player_market_key (event_hour + live); ambiguous collision drop; O/U resolve; milestone de-vig; multi-book consensus
    │   ├── flat_line.py
    │   ├── ev_pipeline.py
    │   ├── ev_display.py       # ranked table: Lg, Game ([team] bracket), Hit%, EV%, DK, FD, Src (ms🔶 milestone), Live
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
        ├── conftest.py
        ├── fixtures/
        ├── integration/
        └── unit/             # incl. golden snapshots, property (test_math_properties), fixture-shape, match-stats coverage tests
```

**EV data flow:** `./ev` or `python -m core.pipeline_runner` → league loop (NBA, MLB, WNBA) × sources (dfs: betr; books: dk, fd, espn) → in-memory merge → `normalize.py` (master + wrapped normalized + `unified_master_board.json`; normalized rows carry optional `event_start` UTC ISO and display `game` from each book's event metadata) → `ev_pipeline.py` (`load_comparison_inputs` / `run_ev_scan` honor `active_sources` on partial scrapes so stale off-run boards are not mixed in; `persist_match_diagnostics` with `by_league` → `match_report.json`; `run_id` check → `ev_opportunities.json` incl. `is_live`, per-book odds fields (`dk_*`/`fd_*`/`espn_*`), combo flags (`ou_ms_combo`, `*_milestone_one_sided`), and milestone caveat fields; rotate + `ev_run_diff.json`) · `scrape_coverage.json` per run. Sharp resolution per Betr line: `_filter_sharp_props_by_match_context` on DK/FD/ESPN normalized props (`build_match_context_key` with hour-floor `event_hour` — sole game discriminator; at Betr line `0.5`, per-book borrow of equivalent `hits`/`total_bases` o/u when native o0.5 missing — relabeled shallow copy, milestone rows excluded) — **per-book** O/U-else-milestone (`resolve_book_sharp_quote`), assembled into one row (`resolve_multi_book_sharp_quote`); ladder lookup via `build_player_market_key` (optional `|event_hour` + `|live` suffix; conflicting same-line odds drop the key). `multi_book_consensus` when 2+ books have exact O/U (N-book weighted de-vig via `SHARP_BOOK_WEIGHTS_*`); cross-book O/U+milestone combos keep milestone display-only for EV. Milestone (`N+`) gap-filler only when that book's O/U missing or DK-extrapolated — exact milestone overs admitted when hold-aware de-vig clears `MILESTONE_MIN_FAIR_OVER`. Partial book runs (e.g. `--books fd` or `--books espn`) need at least one sharp book with props. MLB: DK ingests pregame + in-progress events via `DK_MLB_LIVE_STAT_CATEGORIES` (8 batter tabs; per-market `None` would skip that tab — all set as of walks `9536`); each DK prop carries display `game` + `event_start` from the league slate; FD ingests pregame O/U + MLB milestone boards with `event_start` + `game` from `build_event_start_map` / `build_event_game_map`; ESPN ingests pregame MLB O/U via its GraphQL read chain with `event_start` + canonical `game`; Betr ingests scheduled + `IN_PROGRESS` from the same `getUpcomingEventsV2` call when `BETR_BASE_HEADERS` include app-parity client headers (`api_headers.py`), tagging `event_start` from event `date`. Live Betr props require matching `|live` sharp ladder keys (pregame sharp lines for the same hour are ignored). WNBA: pregame only; FD skipped.


## 6. Roadmap

### Next up (sequenced — live-first, then breadth)

1. **Live MLB — ESPN:** Gate event discovery on the per-game `status` already captured (`config/espn_competitions.py:120`) so in-play games are scraped, and emit `is_live=True` rows (mirror DK `scrapers/sportsbooks/dk_engine.py:98-111,196`); confirm `EventDrawerContent` returns live O/U ladders for in-play events. **Why first:** Betr serves live props, but sharp consensus (`engine.py` `multi_book_consensus`) currently collapses to DK alone during live games — this restores a 2nd live sharp. Cheap (signal already in hand). User-owned: capture which `status` values mean in-play during a live game.
2. **Live MLB — FanDuel:** Flip the deliberate in-play skip (`scrapers/sportsbooks/fd_api.py:439-440`, `event_page_in_play` `:418-422` already reads `inPlay`) into handling; emit `is_live=True` rows; confirm event-page tabs return live ladders (vs pregame-only). Brings live sharp consensus to 3 books (DK+ESPN+FD). User-owned: confirm an in-play FD tab fetch returns live ladders.
3. **New sharp book — Caesars (breadth):** Onboard Caesars for live MLB props — new `*_api`/`*_engine`/`*_parser` trio + `config/` competitions/markets + `config/team_abbrev.py` canon + `config/pipeline_sources.py` (mirror DK/FD/ESPN layout). Chosen for strong live MLB prop coverage → more data points for the weighted multi-book consensus to confirm +EV props. Feeds the existing **Additional sharp books** weighting entry below (`SHARP_BOOK_WEIGHTS_*`).

### Open

* **Betr live fixture refresh:** Replace synthetic `tests/fixtures/betr_mlb_live.json` with a trimmed real DevTools capture (optional follow-up from [docs/plans/betr-live-events-feed.md](docs/plans/betr-live-events-feed.md)).
* **MLB props (pregame v2):** **Deferred:** `HITTER_STRIKEOUTS` (milestone-only on DK). Flat/push pitching K + milestone penalty — see [mlb.md](docs/betting_odds/mlb.md).
* **MLB milestone-only tabs (remaining):** `HITTER_STRIKEOUTS` (`17849`); pitching K push pairing (`15221` + `17323`) — parser/scrape gaps; general exact-milestone +EV admission is shipped (see Completed).
* **Additional sharp books:** Extend weighted consensus for more books beyond DK/FD/ESPN (`SHARP_BOOK_WEIGHTS_*`).
* **Granular promos / non-REGULAR Betr types:** Parse `MINI_BOOSTED`, `BOOSTED`, `EDGE`, etc.; store raw multipliers and alternate breakevens (wide-fetch fields already on master board).
* **Race-to-place parlay checker:** Build same parlay on DK/FD, compare to Betr promo multipliers (2-leg 3x→4x through 8-leg 100x→150x), hardcoded +EV threshold for take/pass.
* **Open-parlay live checker (`./check` / `./parlays` — short name TBD):** Scan the **Betr account** for open/pending parlays, cross-reference each leg against current live odds for those props, and output the live valuation per parlay. Needs authenticated account/bet-history access (distinct from the public odds GraphQL) — open question whether Betr exposes a placed-bets endpoint. Distinct from the race-to-place checker above (that builds hypothetical parlays on DK/FD; this reads bets already placed).
* **Promo prop scanner (`./promos`):** Find Betr promo props (discount, nuke, etc.), scrape their odds, and display prop type + odds + multiplier. Multiplier discovery: read the effective per-prop multiplier by building a **2-leg parlay** pairing the promo prop with a known-normal prop and backing out the promo leg (e.g. 2-man normal = 3x, nuke = 6x, so a discount prop in a 2-man reads ~3x). Builds on the **Granular promos / non-REGULAR Betr types** parsing entry above (raw multipliers already on the wide-fetch master board).
* **FanDuel two-sided MLB milestones:** If live captures show Yes/No runners on milestone boards, ingest as true O/U at line `N-0.5` (multiplicative de-vig + consensus) — v1 is one-sided over-only ([docs/plans/archive/fd-milestone-props.md](docs/plans/archive/fd-milestone-props.md) open question).
* **FanDuel NBA/WNBA milestones:** `TO_SCORE_*` / made-threes / double-double boards after FD WNBA slate + NBA milestone families ship (deferred from [docs/plans/archive/fd-milestone-props.md](docs/plans/archive/fd-milestone-props.md)).
* **Same-name player disambiguation:** When normalized player names collide at the same `event_hour` with conflicting sharp odds, ladders drop the key today — future work could use book player IDs / team context to split collisions instead of failing closed.
* **FanDuel 1+ hit milestone → o0.5 total_bases:** Map FD `TO_RECORD_*` / `PLAYER_TO_RECORD_*` one-sided hit milestones as an o0.5 total_bases source (deferred from o0.5 hits↔tb equivalence — o/u borrow only today).

### Completed / archived

* Betr GraphQL scrape + parser + normalization pipeline (`betr_api.py`, wide `LeagueUpcomingEvents` fetch).
* Per-side Betr O/U EV: `allowedOptions` → parser side flags → `compare_betr_vs_draftkings` (under-only / over-only +EV when one side offered).
* DK markets API scrape via `dk_api.py` / `dk_engine.py` + `dk_parser.py` (httpx, no Playwright).
* **DK scrape hardening (Akamai 403):** per-event `fetch_event_all_markets`; `DK_MARKETS_MAX_CONCURRENT` semaphore (default 6); 403/429 retry/backoff; browser-like headers; league warm-up skipped on auto-discover — [docs/betting_odds/draftkings.md](docs/betting_odds/draftkings.md).
* `normalize.py` active platforms: Betr + DraftKings + FanDuel + ESPN; Dabble archived.
* `ev_pipeline.py` loads `{betr,dk,fd,espn}_normalized.json` (optional `active_sources` filter on partial scrapes) → `compare_betr_vs_draftkings` → `ev_opportunities.json`; ranked plays table via `ev_display.py`.
* Offline pytest suite: `tests/unit/test_{betr,dk,fd,espn}_*`, `test_ev_engine`, `test_ev_pipeline`, `test_ev_display`, `test_line_adjustment`, `test_line_adjustment_multi_book`, `test_milestone_ev_board`, `test_pipeline_runner`, `test_pipeline_sources`, `test_normalize`, `test_math_utils`, `test_team_abbrev`, `test_fd_game_map`, `test_match_keys`; fixtures incl. `espn_lines_games.json`, `espn_event_page.json`, `espn_event_section_{pitcher,batter}.json`, `espn_drawer_{pitcher_strikeouts,batter_hits}.json`, `betr_wnba_pregame.json`, `dk_milestone_ladder.json`, `fd_league_nba_events.json`, `fd_league_mlb_events.json`, `fd_event_*_player_{points,rebounds,assists}.json`, `fd_event_*_pitcher_props.json`, `fd_event_35733870_milestones.json`; plus golden EV snapshots, `test_math_properties` (property-based), `test_fixture_shapes`, and `test_match_stats` coverage tests. **515** tests offline (2026-06-26).
* Betr breakeven aligned at **-120** across `math_utils`, parser side markers, and EV engine.
* Daily refresh orchestrator: `core/pipeline_runner.py` (`run_refresh`) — multi-league loop, `--dfs` / `--books` / `--leagues`, fresh-only runs with `run_id`, `core/pipeline_scrape.py`, `config/pipeline_sources.py`; repo-root `./ev` wrapper.
* Betr `--league` case normalization: `_normalize_betr_league` + `BetrEngine` uppercase GraphQL enum; GraphQL `errors` logged on invalid league — fixes empty MLB slate when invoking `./ev --league mlb`.
* Pipeline `--min-ev` / `--plus-ev-only`: filter ranked output to `ev > min_ev`; `plus_ev` flag on each row; default `min_ev=0` shows top-N including negative EV.
* Ranked plays table: `ev_display.py` — 12-column layout (Lg, Game with bracketed team, widened Stat, Hit%, EV%, DK/FD O/U, Src, Live).
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
* ESPN / TheScore Bet: GraphQL persisted-query `espn_*` scrape (anonymous JWE mint) → parse/normalize, `BOOK_SOURCES` + `--books espn`, N-book `_consensus_sharp_quote` + `SHARP_BOOK_WEIGHTS_ESPN`; MLB GraphQL fixtures/tests; API validated live 2026-06-22; platform doc [docs/betting_odds/espn.md](docs/betting_odds/espn.md) · [docs/plans/archive/espn.md](docs/plans/archive/espn.md).
* Multi-book consensus weights: `load_sharp_book_weights()` in `line_adjustment.py` — `SHARP_BOOK_WEIGHTS_DK` / `SHARP_BOOK_WEIGHTS_FD` / `SHARP_BOOK_WEIGHTS_ESPN` env vars (default 1.0 each).
* **Plan archive enforcement (pre-PR):** `scripts/archive_plan.sh` moves shipped handoffs to `docs/plans/archive/`; `scripts/check_plan_archived.sh` + `open_pr.sh` + CI block shipping PRs with active handoffs (replaces post-merge `archive-plan` workflow).
* **MLB live batter props (DK):** DK pregame+live event discovery; `DK_MLB_LIVE_STAT_CATEGORIES` + `configured_live_stat_categories_for_league` (8/8 live batter IDs incl. `walks` `9536`); `is_live` through DK parser → `ev_opportunities.json` + **Live** column in `ev_display` — [docs/plans/archive/mlb-live-props-dk.md](docs/plans/archive/mlb-live-props-dk.md).
* **Betr live MLB props (headers + engine):** App-parity GraphQL headers in `BETR_BASE_HEADERS` (`jurisdiction`, `channel`, `fantasy-api-version`, etc.) — same `LeagueUpcomingEvents` / `getUpcomingEventsV2` returns `IN_PROGRESS` + `isLive=true` (not a separate operation). `iter_live_events` / `extract_raw_props` merge scheduled + live; `betr_api` status/isLive probe; `is_live` through parser → EV — [docs/betting_odds/betr.md](docs/betting_odds/betr.md) (headers), [docs/plans/betr-live-events-feed.md](docs/plans/betr-live-events-feed.md) (resolved; fixture refresh optional).
* **DK live subCategoryId probe tooling:** `dk_subcategory_discovery.py`; `probe_dk_subcategories --league mlb --live --discover`; `probe_dk_discover --live` — live MLB tabs use different IDs than pregame ([mlb.md](docs/betting_odds/mlb.md)).
* **DK config rename (NBA):** `DK_NBA_*_STAT_CATEGORIES` / `DK_NBA_MILESTONE_STAT_CATEGORIES` / `DK_NBA_PENDING_STAT_CATEGORIES` (was generic `DK_STAT_CATEGORIES` names).
* **MLB pregame props (DK ship):** 13 markets Betr ↔ DK (`DK_MLB_STAT_CATEGORIES`, `MLB_ENABLED_MARKETS`, incl. `doubles`); FanDuel MLB wired later (see FanDuel MLB bullet above).
* **WNBA slate (Betr ↔ DK):** `PIPELINE_LEAGUES` + `BETR_TO_DK_LEAGUE["WNBA"]`; `DK_LEAGUE_SLATES["wnba"]` (`94682`/`4511`); explicit `DK_WNBA_*` stat aliases; per-league `--nba`/`--mlb`/`--wnba` shorthands (`merge_leagues_from_args`); `ev_display` **Lg** column; pregame only (FD auto-skipped); `betr_api` `__main__` forwards `[LEAGUE]` argv — [docs/plans/archive/wnba-betr-dk-slate.md](docs/plans/archive/wnba-betr-dk-slate.md).
* **Milestone +EV board admission:** Hold-aware milestone de-vig (`devig_milestone_fair_over`, `estimate_ou_hold`) and dynamic fair-over gate (`MILESTONE_MIN_FAIR_OVER`, `MILESTONE_ASSUMED_HOLD` in `settings.py`); only exact-threshold milestones on the board; JSON flags (`not_true_devig`, `milestone_devig_method`, `milestone_admitted`); CLI **Src** `ms🔶`; book-agnostic milestone ladder + `sharp_books` provenance — [docs/plans/archive/milestone-ev-board.md](docs/plans/archive/milestone-ev-board.md).
* **FanDuel MLB milestone ingestion:** `parse_player_milestone_market_type` + `flatten_player_milestone_market` in `fd_markets.py` / `fd_api.py`; `FD_MILESTONE_MARKETS_BY_LEAGUE` (MLB hits, total bases, runs, RBI, H+R+RBI); `fd_parser` milestone fields; `group_fd_line_rows` keys by `line_kind`; fixture `fd_event_35733870_milestones.json`; tests in `test_fd_markets`, `test_fd_api`, `test_normalize_fd`, `test_milestone_ev_board` — EV layer unchanged (book-agnostic admission) — [docs/plans/archive/fd-milestone-props.md](docs/plans/archive/fd-milestone-props.md).
* **Cross-book game + live snapshot matching (superseded):** `build_player_market_key` / `normalize_game_key` in `line_adjustment.py` — sharp ladders keyed by `player|market|[game]|[live]`; DK scrape tags `game` + `event_id` via `game_key_from_dk_event` / `build_event_game_map` (`dk_api.py`, `dk_engine.py`); `dk_parser` propagates; prevents live Betr props from resolving against pregame sharp lines on back-to-back same-team slates; tests `test_match_keys`, `test_dk_game_map`, `test_ev_engine` (Lowe regression). **Superseded** by event-hour match gate below — `game` retained for display only.
* **Betr event-start validation:** `event_start` UTC ISO on normalized props (Betr `date`, DK `startEventDate`, FD `openDate`); `build_event_start_map` in `dk_api.py` and `fd_competitions.py`; `fd_engine._fetch_league_slate` single-fetch refactor; superseded by match-context resolution below — [docs/plans/archive/betr-event-start-validation.md](docs/plans/archive/betr-event-start-validation.md).
* **Match-context sharp resolution:** `build_match_context_key` + per-Betr `_filter_sharp_props_by_match_context` in `engine.py` / `line_adjustment.py` (replaces post-hoc `_build_event_start_idx` hour mismatch filter); ladder rows + `ResolvedSharpQuote.sharp_event_start`; Freeman/series, DH game 1/2, pregame fail-closed tests — [docs/plans/archive/match-context-resolution.md](docs/plans/archive/match-context-resolution.md).
* **o0.5 hits ↔ total_bases equivalence:** `O05_EQUIVALENT_MARKETS` / `equivalent_o05_markets` in `market_maps.py`; per-book borrow in `_filter_sharp_props_by_match_context` (`engine.py`) — bidirectional o/u at line `0.5` only, prefer native per book, relabeled shallow copy; `test_hits_total_bases_o05_equiv` — [docs/plans/archive/map-o05-hits-total-bases.md](docs/plans/archive/map-o05-hits-total-bases.md).
* **Cross-book team abbreviation canonicalization (display):** `config/team_abbrev.py` — `TEAM_ABBR_ALIASES` maps DK/ESPN deviating codes (e.g. `CWS`→`CHW`) to betr vocabulary; `game_key_from_full_names` for FanDuel; wired in `fd_competitions.build_event_game_map`, `espn_competitions._event_game_key`; `test_team_abbrev`, `test_fd_game_map` — display `game` strings align across books; match gate unaffected (#66).
* **Event-hour match gate:** Removed `normalize_game_key` / `game` segment from `build_match_context_key` and `build_player_market_key`; UTC `event_hour` (`iso[:13]`) is the sole game discriminator; abbreviation vocabulary mismatches no longer silently drop matches; DH/series separation via hour-floor; `test_match_keys` (abbrev-variant collision + different-hour separation) — [docs/plans/archive/match-gate-event-hour.md](docs/plans/archive/match-gate-event-hour.md).
* **Ambiguous sharp-ladder collision drop:** `build_player_market_ladder` / milestone ladder builders drop `pm_key` when same-line rows carry conflicting odds (same-name player clash) instead of last-write-wins; `test_line_adjustment.test_conflicting_collision_drops_pm_key_from_ladder`.
* **FanDuel game display tagging:** `build_event_game_map` in `fd_competitions.py`; `fd_engine._fetch_league_slate` returns `(event_ids, start_map, game_map)`; `fd_parser` propagates `game` on normalized rows; unmapped FD team names skip display only.
* **Per-book sharp resolution (one row, O/U + milestone combo):** `resolve_book_sharp_quote` / `resolve_multi_book_sharp_quote` in `line_adjustment.py` — each book independently prefers O/U else milestone, assembled into one EV row with per-book odds columns and `ou_ms_combo` display flags (cross-book milestone display-only when the other book has O/U) — [docs/plans/archive/per-book-sharp-resolution.md](docs/plans/archive/per-book-sharp-resolution.md) (#61).
* **Engine regression safety net:** golden EV-output snapshots, coverage-gap unit tests, and property-based math tests (`test_math_properties.py`, `test_fixture_shapes.py`, `test_match_stats.py`); suite now **515** offline tests — [docs/plans/archive/engine-safety-net.md](docs/plans/archive/engine-safety-net.md) (#69).
