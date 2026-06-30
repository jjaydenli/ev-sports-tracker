# MLB player props (Betr + DraftKings)

Pregame and live batter O/U props for the EV pipeline. Live discovery is standing behavior on `./ev --leagues mlb` (no CLI flag). Unset live IDs (`None`) skip that market on in-game events; pregame scrape is unchanged.

## Enabled O/U markets (full pregame slate)

All rows below are in `DK_MLB_STAT_CATEGORIES`, `MLB_ENABLED_MARKETS` (Betr parser), and scraped on `./ev --league MLB`.

| Canonical | Betr key | DK subCategoryId | DK tab label |
|-----------|----------|------------------|--------------|
| `hits` | `HITS` | 6719 | Hits O/U |
| `total_bases` | `TOTAL_BASES` | 6607 | Total Bases O/U |
| `h+r+rbi` | `HITS_RUNS_RUNS_BATTED_IN` | 17406 | Hits + Runs + RBIs O/U |
| `runs` | `RUNS` | 17407 | Runs O/U |
| `singles` | `SINGLES` | 17409 | Singles O/U |
| `doubles` | `DOUBLES` | 17410 | Doubles O/U |
| `walks` | `WALKS` | 17411 | Walks (Batter) O/U |
| `earned_runs` | `EARNED_RUNS` | 17412 | Earned Runs Allowed O/U |
| `total_outs` | `TOTAL_OUTS` | 17413 | Outs O/U |
| `strikeouts` | `STRIKEOUTS` | 15221 | Strikeouts Thrown O/U |
| `pitching_walks` | `PITCHING_WALKS` | 15219 | Walks Allowed O/U |
| `hits_allowed` | `HITS_ALLOWED` | 9886 | Hits Allowed O/U |
| `rbi` | `RUNS_BATTED_IN` | 8025 | RBIs O/U |

**Deferred v2:** `HITTER_STRIKEOUTS` (Betr) — DK milestone-only `17849`; enable with milestone EV + over-side penalty.

Crosswalk + milestone refs: `backend/config/discovery/mlb.yaml`.

### Milestone tabs (reference — not scraped in full slate)

| Betr key | DK subCategoryId | Notes |
|----------|------------------|-------|
| `STRIKEOUTS` | 17323 | Pair with 15221 for push/flat K lines (TBD) |
| `HITTER_STRIKEOUTS` | 17849 | Defer v2 |
| `HITS_ALLOWED` | 19457 | Reference; O/U at 9886 |

## Live batter O/U

Live scrape uses `DK_MLB_LIVE_STAT_CATEGORIES` in `backend/config/dk_subcategories.py` — batter O/U only (no pitcher live markets). **DK live tabs often use different subCategoryIds than pregame** (e.g. total bases `9506` live vs `6607` pregame). Copy the pregame ID only when DevTools confirms DK reuses it.

| Canonical | Betr key | DK live subCategoryId | Pregame ID |
|-----------|----------|------------------------|------------|
| `hits` | `HITS` | 9502 | 6719 |
| `total_bases` | `TOTAL_BASES` | 9506 | 6607 |
| `h+r+rbi` | `HITS_RUNS_RUNS_BATTED_IN` | 12152 | 17406 |
| `runs` | `RUNS` | 17475 | 17407 |
| `singles` | `SINGLES` | 17471 | 17409 |
| `doubles` | `DOUBLES` | 17472 | 17410 |
| `walks` | `WALKS` | 9536 | 17411 |
| `rbi` | `RUNS_BATTED_IN` | 9505 | 8025 |

EV rows from live props carry `is_live: true`; the ranked table shows **L** in the Live column.

## Pipeline

```bash
cd backend
./ev --league MLB --skip-fd
```

- `--league MLB` drives Betr `LeagueUpcomingEvents` and DK slate key `mlb` (13 O/U prop tabs per pregame event; live batter tabs per `DK_MLB_LIVE_STAT_CATEGORIES`).
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
- Pregame props: `DK_MLB_STAT_CATEGORIES` in `backend/config/dk_subcategories.py`.
- Live props: `DK_MLB_LIVE_STAT_CATEGORIES` (same file); event discovery uses `NOT_STARTED` + `IN_PROGRESS` / `STARTED` (`LIVE_EVENT_STATUSES`).

```bash
# Pregame event — verify DK_MLB_STAT_CATEGORIES
python -m scripts.probe_dk_subcategories <event_id> --league mlb

# Live (in-game) event — DK uses different subCategoryIds on many tabs
python -m scripts.probe_dk_subcategories <live_event_id> --league mlb --live --discover
```

`--discover` scans live ID ranges and prints a pregame vs live comparison table. To verify configured live IDs: `--live` without `--discover`. DevTools Network on `event/eventSubcategory/v1/markets` → `clientMetadata/subCategoryId` also works.

## Capture checklist (new markets)

Manifest: `backend/config/discovery/mlb.yaml`.

1. **DK event id** — game URL or league slate.
2. **DK prop subCategoryIds** — DevTools per stat tab; verify with `probe_dk_subcategories`.
3. **Betr keys** — `LeagueUpcomingEvents` fixture → `tests/fixtures/betr_mlb_pregame.json` (pregame) or `tests/fixtures/betr_mlb_live.json` (live).
4. **Fixtures** — `tests/fixtures/dk_markets_mlb_*.json`; slate with live event → `tests/fixtures/dk_league_mlb_events_with_live.json`.
