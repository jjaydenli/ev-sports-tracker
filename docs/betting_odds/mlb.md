# MLB player props (Betr + DraftKings)

Pregame and live batter O/U props for the EV pipeline. Live discovery is standing behavior on `./ev --leagues mlb` (no CLI flag). Unset live IDs (`None`) skip that market on in-game events; pregame scrape is unchanged.

## Enabled O/U markets (full pregame slate)

All rows below are in `DK_MLB_PREGAME_STAT_CATEGORIES`, `MLB_ENABLED_MARKETS` (Betr parser), and scraped on `./ev --league MLB`.

| Canonical | Betr key | DK subCategoryId | DK tab label |
|-----------|----------|------------------|--------------|
| `hits` | `HITS` | 6719 | Hits O/U |
| `total_bases` | `TOTAL_BASES` | 6607 | Total Bases O/U |
| `h+r+rbi` | `HITS_RUNS_RUNS_BATTED_IN` | 17406 | Hits + Runs + RBIs O/U |
| `runs` | `RUNS` | 17407 | Runs O/U |
| `singles` | `SINGLES` | 17409 | Singles O/U |
| `doubles` | `DOUBLES` | 17410 | Doubles O/U |
| `batting_walks` | `WALKS` | 17411 | Walks (Batter) O/U |
| `earned_runs` | `EARNED_RUNS` | 17412 | Earned Runs Allowed O/U |
| `total_outs` | `TOTAL_OUTS` | 17413 | Outs O/U |
| `pitching_strikeouts` | `STRIKEOUTS` | 15221 | Strikeouts Thrown O/U |
| `pitching_walks` | `PITCHING_WALKS` | 15219 | Walks Allowed O/U |
| `hits_allowed` | `HITS_ALLOWED` | 9886 | Hits Allowed O/U |
| `rbi` | `RUNS_BATTED_IN` | 8025 | RBIs O/U |

**DK-only pregame O/U** (in `DK_MLB_PREGAME_STAT_CATEGORIES`, not `MLB_ENABLED_MARKETS` — scraped from DK but no Betr line to match):

| Canonical | DK subCategoryId | DK tab label |
|-----------|------------------|--------------|
| `stolen_bases` | 17408 | Stolen Bases O/U |
| `h+bb+er` | 19459 | Hits + Walks + Earned Runs O/U |

**Deferred v2:** `HITTER_STRIKEOUTS` (Betr) → `batting_strikeouts` (canonical) — DK pregame milestone `17849` (wired); enable Betr-side with milestone EV + over-side penalty.

### Pregame milestone (verified 2026-07-27)

`DK_MLB_PREGAME_MILESTONE_STAT_CATEGORIES` — 17 batter N+ tabs plus `pitching_strikeouts` (`17323`, sole N+ pitcher milestone). Full id table in [draftkings.md](draftkings.md). Combo keys (`xbh`, `h+r+sb`, `h+sb`, `h+bb+sb`, `r+rbi`) are DK-only until Betr offers matching markets.

### Milestone policy

N+ milestone tabs are over-only for de-vig: the v2 parser applies an over-side penalty (example
-180 → ~-145). Pitching K O/U (`15221`) pairs with Strikeouts Thrown Milestones (`17323`) for
integer/push lines (flat-line policy TBD in `core/flat_line.py`).

DK also posts pitcher milestone tabs labeled "X or Fewer" (an under-side threshold format). Those
tabs are **not wired** — the parser only reads `N+` labels (`MILESTONE_THRESHOLD_RE`), so an "X or
Fewer" tab fetches successfully but contributes zero rows. See the DK-only reference table below.

### Milestone tabs (reference — defer v2 or parked)

| Betr key | DK subCategoryId | Notes |
|----------|------------------|-------|
| `HITTER_STRIKEOUTS` | 17849 | Wired pregame milestone; Betr enablement deferred v2 |
| `HITS_ALLOWED` | 19457 | Reference; O/U at 9886 |

### DK-only, captured, not wired

Confirmed ids parked on capability — not in any `dk_subcategories.py` map.

| DK tab | Pregame id | Live id | Why not wired |
|--------|------------|---------|---------------|
| To Record A Win | 9884 | 12964 | Binary O/U tab with no numeric line; parser and EV engine need a line to match |
| Hits Allowed (X or Fewer) | 19457 | 17478 | Under-side milestone; parser is `N+` only |
| Walks Allowed (X or Fewer) | 19456 | 17484 | same |
| Earned Runs (X or Fewer) | 19458 | 17491 | same |
| Hits + Walks + Earned Runs (X or Fewer) | 19460 | 19572 | same |

### Live batter milestone (verified 2026-07-23)

`DK_MLB_LIVE_MILESTONE_STAT_CATEGORIES` in `backend/config/dk_subcategories.py` — all 12 batter markets verified on a live KC@DET game, plus live pitcher `pitching_strikeouts` milestone (`17481`, verified 2026-07-27). Full id table in [draftkings.md](draftkings.md). Includes `batting_strikeouts` (`17490`, distinct from the pregame `17849` above) plus three markets Betr does not currently offer (`home_runs`, `stolen_bases`, `triples`) — stored for when/if Betr adds them; ESPN already has canonical `home_runs`/`stolen_bases` entries.

## Live batter + pitcher O/U

Live scrape uses `DK_MLB_LIVE_STAT_CATEGORIES` in `backend/config/dk_subcategories.py`. **DK live tabs often use different subCategoryIds than pregame** (e.g. total bases `9506` live vs `6607` pregame). Copy the pregame ID only when DevTools confirms DK reuses it.

| Canonical | Betr key | DK live subCategoryId | Pregame ID |
|-----------|----------|------------------------|------------|
| `hits` | `HITS` | 9502 | 6719 |
| `total_bases` | `TOTAL_BASES` | 9506 | 6607 |
| `h+r+rbi` | `HITS_RUNS_RUNS_BATTED_IN` | 12152 | 17406 |
| `runs` | `RUNS` | 17475 | 17407 |
| `singles` | `SINGLES` | 17471 | 17409 |
| `doubles` | `DOUBLES` | 17472 | 17410 |
| `batting_walks` | `WALKS` | 9536 | 17411 |
| `rbi` | `RUNS_BATTED_IN` | 9505 | 8025 |
| `stolen_bases` | — (DK-only) | 17474 | 17408 |
| `pitching_strikeouts` | `STRIKEOUTS` | 12960 | 15221 |
| `earned_runs` | `EARNED_RUNS` | 19874 | 17412 |
| `hits_allowed` | `HITS_ALLOWED` | 12962 | 9886 |
| `pitching_walks` | `PITCHING_WALKS` | 12963 | 15219 |
| `total_outs` | `TOTAL_OUTS` | 17476 | 17413 |
| `h+bb+er` | — (DK-only) | 19913 | 19459 |

Pitcher O/U verified live 2026-07-25. `h+bb+er` (hits + walks + earned runs) has no Betr equivalent, so it is still requested from DK like any other live tab, but is absent from `MLB_ENABLED_MARKETS` (`parsers/betr_parser.py`) and so never produces an EV row until a DFS app offers a matching market. Capture-don't-restrict: leave it wired.

EV rows from live props carry `is_live: true`; the ranked table shows **L** in the Live column.

## Pipeline

```bash
cd backend
./ev --league MLB --skip-fd
```

- `--league MLB` drives Betr `LeagueUpcomingEvents` and DK slate key `mlb` (15 pregame O/U + 18 pregame milestone tabs per event; live tabs per `DK_MLB_LIVE_STAT_CATEGORIES`).
- FanDuel is auto-skipped (no comparable MLB props).
- Pitching K integer/push lines: flat-line policy TBD (`core/flat_line.py`).

## Betr

- League enum: `MLB`.
- Pregame: `status == SCHEDULED`, `isLive == false`, `marketStatus == OPENED`.
- Live: `status == IN_PROGRESS` (`BETR_LIVE_EVENT_STATUSES`), `isLive == true`, `marketStatus == OPENED`. Line field: `value` (fixture-confirmed; `currentValue` is stat count, not the O/U line). Frozen in-game markets arrive as `marketStatus == SUSPENDED` and are dropped (can't be placed) — only `OPENED` live props reach the board.
- Live source: the **same** `getUpcomingEventsV2` operation returns `IN_PROGRESS` events, but only when the request carries app-parity headers (`jurisdiction`, `channel`, `fantasy-api-version`); without them the feed is pregame-only. See `docs/betting_odds/betr.md` §GraphQL request headers.
- Parser gate: `MLB_ENABLED_MARKETS` in `backend/parsers/betr_parser.py`.

## DraftKings

- Slate: `DK_LEAGUE_SLATES["mlb"]` — `league_id` **84240**, `slate_subcategory_id` **4519**.
- Pregame props: `DK_MLB_PREGAME_STAT_CATEGORIES` and `DK_MLB_PREGAME_MILESTONE_STAT_CATEGORIES` in `backend/config/dk_subcategories.py`.
- Live props: `DK_MLB_LIVE_STAT_CATEGORIES` (same file); event discovery uses `NOT_STARTED` + `IN_PROGRESS` / `STARTED` (`LIVE_EVENT_STATUSES`).

```bash
# Pregame event — verify DK_MLB_PREGAME_STAT_CATEGORIES
python -m scripts.verify_dk_subcategories --event-id <event_id> --league mlb

# Live (in-game) event — DK uses different subCategoryIds on many tabs
python -m scripts.verify_dk_subcategories --event-id <live_event_id> --league mlb --live

# Confirm ids read off DevTools before adding them to config
python -m scripts.verify_dk_subcategories --event-id <event_id> --verify <id> [<id> ...]
```

To discover unknown ids, read `clientMetadata/subCategoryId` off the DevTools Network request for `event/eventSubcategory/v1/markets`, then confirm each with `--verify` above.

## Capture checklist (new markets)

1. **DK event id** — game URL or league slate.
2. **DK prop subCategoryIds** — DevTools per stat tab; verify with `verify_dk_subcategories`.
3. **Betr keys** — `LeagueUpcomingEvents` fixture → `tests/fixtures/betr_mlb_pregame.json` (pregame) or `tests/fixtures/betr_mlb_live.json` (live).
4. **Fixtures** — `tests/fixtures/dk_markets_mlb_*.json`; slate with live event → `tests/fixtures/dk_league_mlb_events_with_live.json`.
