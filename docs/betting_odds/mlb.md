# MLB player props (Betr + DraftKings)

Pregame MLB props for the EV pipeline. **Live/in-game props are deferred** until Betr and DK offer them on the slate (see roadmap in `project_context.md` §6).

## Enabled O/U markets (full slate)

All rows below are in `DK_MLB_STAT_CATEGORIES`, `MLB_ENABLED_MARKETS` (Betr parser), and scraped on `./ev --league MLB`.

| Canonical | Betr key | DK subCategoryId | DK tab label |
|-----------|----------|------------------|--------------|
| `hits` | `HITS` | 6719 | Hits O/U |
| `total_bases` | `TOTAL_BASES` | 6607 | Total Bases O/U |
| `h+r+rbi` | `HITS_RUNS_RUNS_BATTED_IN` | 17406 | Hits + Runs + RBIs O/U |
| `runs` | `RUNS` | 17407 | Runs O/U |
| `singles` | `SINGLES` | 17409 | Singles O/U |
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

## Pipeline

```bash
cd backend
./ev --league MLB --skip-fd
```

- `--league MLB` drives Betr `LeagueUpcomingEvents` and DK slate key `mlb` (12 O/U prop tabs per event).
- FanDuel is auto-skipped (no comparable MLB props).
- Pitching K integer/push lines: flat-line policy TBD (`core/flat_line.py`).

## Betr

- League enum: `MLB`.
- Pregame: `status == SCHEDULED`, `isLive == false`, `marketStatus == OPENED`.
- Parser gate: `MLB_ENABLED_MARKETS` in `backend/parsers/betr_parser.py`.

## DraftKings

- Slate: `DK_LEAGUE_SLATES["mlb"]` — `league_id` **84240**, `slate_subcategory_id` **4519**.
- Props: `DK_MLB_STAT_CATEGORIES` in `backend/config/dk_subcategories.py`.

```bash
python -m scripts.probe_dk_subcategories <event_id> --league mlb
```

## Capture checklist (new markets)


1. **DK event id** — game URL or league slate.
2. **DK prop subCategoryIds** — DevTools per stat tab; verify with `probe_dk_subcategories`.
3. **Betr keys** — `LeagueUpcomingEvents` fixture → `tests/fixtures/betr_mlb_pregame.json`.
4. **Fixtures** — `tests/fixtures/dk_markets_mlb_*.json`.

## Live props (future)

When live slates exist, add `--live` mode:

- Betr: `IN_PROGRESS` events, `isLive` projections, `current_value` as line.
- DK: `STARTED` events via `extract_event_ids(statuses=…)`.
