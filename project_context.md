# Master Project Context: Multi-Platform EV Betting Engine

**Last verified:** 2026-07-15

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

Platform depth: [docs/betting_odds/](docs/betting_odds/). §3 is routing only — IDs, guards, and probes live in those docs.

### Betr (primary DFS)

- **Role:** Fixed-payout DFS props; primary DFS source.
- **Code:** `backend/scrapers/dfs/betr/`, `backend/parsers/betr_parser.py`
- **Live:** `IN_PROGRESS` events + `isLive`/`marketStatus` gates; stamps `is_live`, `game`, `event_start`.
- **Probe:** `python -m scrapers.dfs.betr.betr_api [LEAGUE]` (default `NBA`)
- **Detail:** [docs/betting_odds/betr.md](docs/betting_odds/betr.md)

### DraftKings (sharp sportsbook)

- **Role:** Primary sharp O/U + milestone (`N+`) ladders; main input to `core/ladder_index.py` and `core/line_adjustment.py`.
- **Code:** `dk_engine.py`, `dk_api.py`, `dk_parser.py`, `config/dk_subcategories.py`
- **Live (MLB):** Pregame + in-play slates; `DK_MLB_LIVE_STAT_CATEGORIES` (live subCategoryIds differ from pregame).
- **Detail:** [docs/betting_odds/draftkings.md](docs/betting_odds/draftkings.md)

### FanDuel (sharp sportsbook)

- **Role:** Second sharp book. NBA + MLB pregame O/U + MLB milestones. **No live FD MLB** (in-play skipped in `fd_api.py`).
- **Code:** `fd_api.py`, `fd_engine.py`, `fd_parser.py`, `config/fd_markets.py`, `config/fd_competitions.py`
- **Detail:** [docs/betting_odds/fanduel.md](docs/betting_odds/fanduel.md)

### ESPN / TheScore Bet (sharp sportsbook)

- **Role:** Third sharp book (`espn`). GraphQL persisted queries + anonymous JWE auth.
- **Code:** `espn_api.py`, `espn_auth.py`, `espn_engine.py`, `espn_parser.py`, `config/espn_*.py`
- **MLB:** Pregame + live O/U + batter milestones; OPEN-only guard; `_parse_odds` maps `"Even"` → `+100`.
- **Detail:** [docs/betting_odds/espn.md](docs/betting_odds/espn.md)

### Dabble (archived)

`backend/archive/dabble/` · [docs/betting_odds/dabble.md](docs/betting_odds/dabble.md)

### League CLI shortcuts

Default: all leagues (NBA, MLB, WNBA). Filter with `--mlb` / `--nba` / `--wnba` and/or `--leagues mlb,wnba` (shorthand unions with `--leagues`; same on `./loop`).

| League | Books | Filter |
|--------|-------|--------|
| MLB | Betr + DK/FD/ESPN (FD pregame only) | `./ev --mlb` |
| WNBA | Betr + DK (FD skipped) | `./ev --wnba` |
| NBA | Betr + DK + FD | `./ev --nba` |

## 4. Quantitative Modeling & Math

- **Display vs matching:** `game` (AWAY@HOME) is UI-only; match gate never reads it. `config/team_abbrev.py` canonicalizes DK/ESPN/FD display keys.
- **Match keys:** `core/ladder_index.py` — `build_match_context_key` → `player|market|league|[event_hour]|[live]`; `build_player_market_key` → `player|market|[event_hour]|[live]`. Pregame: `event_hour` = UTC hour-floor when `event_start` present. Live: omit `event_hour` (`|live` suffix only). Pregame without `event_start` fails closed. Ambiguous same-key+line odds collision drops the `pm_key`.
- **Market mapping:** `PLATFORM_MARKET_MAPPINGS` → `MARKETS` in `config/market_maps.py`.
- **De-vig (O/U):** American odds → implied probs; multiplicative removal in `utils/math_utils.py`.
- **De-vig (milestone):** `devig_milestone_fair_over` in `core/resolution_math.py` (ladder-normalize else hold-shrink; `MILESTONE_MIN_FAIR_OVER` gate).
- **o0.5 equivalence:** `_filter_sharp_props_by_match_context` may borrow `hits`↔`total_bases` at line 0.5 per book (`O05_EQUIVALENT_MARKETS`).
- **EV resolution:** `config/sharp_books.py` registry drives `resolve_book_sharp_quote` in `core/line_adjustment.py`; multi-book assembly in `core/multi_book_resolver.py`. Ladder indexing in `core/ladder_index.py`. `ResolvedSharpQuote` stores `ev_line_kind` + `per_book` (`BookQuote` per book); output JSON flat keys derived via `book_quote()`. Multi-book consensus when 2+ exact O/U (`SHARP_BOOK_WEIGHTS_*`). `DFSSide` / `BETR` in `engine.py` for DFS-side config. One EV row per Betr side. `plus_ev` when `ev > 0`; optional `--min-ev` filters output (`ev >=` threshold, default none).

## 5. Architecture & File Structure

```text
ev-sports-tracker/
├── scripts/                            # check_arch_sync.sh, open_pr.sh
├── docs/design/                        # architecture decision records
├── .github/workflows/ci.yml
├── ev                                    # → backend pipeline_runner
├── loop                                  # ./ev loop; all leagues, no default --min-ev; colored table + toast
└── backend/
    ├── config/                         # headers, market_maps, sharp_books, team_abbrev, settings, *_{subcategories,markets,competitions,queries}, pipeline_sources
    ├── scripts/                        # probe_dk_*, probe_fd_*, probe_espn_*
    ├── utils/                          # math_utils, formatting
    ├── scrapers/
    │   ├── dfs/betr/                   # betr_api, betr_auth, betr_engine, betr_orchestrator
    │   └── sportsbooks/                # dk_*, fd_*, espn_* engines + apis
    ├── parsers/                        # betr, dk, fd, espn parsers + normalize.py
    ├── core/
    │   ├── models.py, engine.py, line_adjustment.py, ladder_index.py, resolution_math.py, multi_book_resolver.py, flat_line.py
    │   ├── ev_pipeline.py, ev_display.py  # ranked JSON + console table (EV% tiers, Stack clusters, MARKET_ABBREV), ev_run_diff.py
    │   ├── pipeline_scrape.py, pipeline_artifacts.py, scrape_result.py
    │   ├── pipeline_timing.py, pipeline_runner.py  # exclusive processed-dir lock
    ├── archive/dabble/
    ├── data/raw|processed/             # gitignored; .pipeline_run.lock for single-writer ./ev
    └── tests/                          # fixtures, integration, unit; 638 tests
```

**EV data flow:** `./ev` (exclusive lock on `data/processed`) → per-league scrape (betr; dk, fd, espn) → `normalize.py` (`unified_master_board.json`) → `ev_pipeline.py` (`ev_opportunities.json`, diffs, coverage) → match-context filter → sharp resolve → consensus → ranked JSON + colored console table (`ev_display.py`). `./loop` re-runs `./ev` (no default `--min-ev`), reprints the table with new-row highlight; toasts only for new `plus_ev` rows (and `ev >=` threshold when `--min-ev` is set).

**Console table vocabulary** (`ev_display.py`): raw `adjustment_method` never renders — `Src` collapses to a real quote (`exact`, `exact·N` = N books corroborating) or an inferred one (`ms🔶` one-sided milestone, `adj` line adjusted off the ladder), unknown → `?`. `Stat` renders `MARKET_ABBREV` (betting notation, keyed on canonical markets); `Side` renders `▲`/`▼`. Book identity and main-vs-alt stay in `board.json`'s `sharp_by_book`, not the terminal.

## 6. Roadmap

### Next up

1. **Live MLB — FanDuel:** Enable in-play handling in `fd_api.py` (skip today at `:439-440`); emit `is_live` rows; confirm live tab ladders.
2. **New sharp book — Caesars:** `*_api`/`*_engine`/`*_parser` + config + `pipeline_sources.py` (mirror DK/FD/ESPN layout).

### Open

- **Betr live fixture refresh:** Replace synthetic `tests/fixtures/betr_mlb_live.json` with DevTools capture.
- **MLB props (pregame v2):** `HITTER_STRIKEOUTS` milestone-only on DK; pitching K flat/push — [mlb.md](docs/betting_odds/mlb.md).
- **MLB milestone-only tabs:** `HITTER_STRIKEOUTS` (`17849`); pitching K push pairing (`15221` + `17323`).
- **Additional sharp books:** Extend weighted consensus beyond DK/FD/ESPN.
- **Granular Betr promos:** `MINI_BOOSTED`, `BOOSTED`, `EDGE`, etc.; alternate breakevens.
- **Race-to-place parlay checker:** DK/FD parlay vs Betr promo multipliers.
- **Open-parlay live checker (`./check`):** Betr open parlays vs live odds (needs bet-history API).
- **Promo prop scanner (`./promos`):** Back out per-prop multiplier via 2-leg construction.
- **FD two-sided MLB milestones:** Yes/No runners → true O/U at `N-0.5`.
- **FD NBA/WNBA milestones:** `TO_SCORE_*` / made-threes / double-double.
- **Same-name player disambiguation:** Book player IDs / team context vs key-drop.
- **FD 1+ hit milestone → o0.5 total_bases:** Map one-sided hit milestones as o0.5 TB source.
