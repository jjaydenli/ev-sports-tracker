# MLB player props (Betr + DraftKings)

Pregame MLB props for the EV pipeline. **Live/in-game props are deferred** until Betr and DK offer them on the slate (see roadmap in `project_context.md` §6).

## v1 markets

| Canonical | Betr key / label | DK subCategoryId |
|-----------|------------------|------------------|
| `hits` | `HITS` / Hits | 6719 |
| `total_bases` | `TOTAL_BASES` / Total Bases | 6607 |

Other MLB props on the Betr board (H+R+RBI, singles, strikeouts, etc.) are ignored until DK posts comparable O/U tabs.

## Pipeline

```bash
cd backend
./ev --league MLB --skip-fd
```

- `--league MLB` drives Betr `LeagueUpcomingEvents` and DK slate key `mlb`.
- FanDuel is auto-skipped (no comparable MLB props).

## Betr

- League enum: `MLB`.
- Pregame: `status == SCHEDULED`, `isLive == false`, `marketStatus == OPENED`.
- v1 projection keys in `BETR_MARKET_MAP` (`backend/config/market_maps.py`).

## DraftKings

- Slate: `DK_LEAGUE_SLATES["mlb"]` — `league_id` **84240**, slate `subcategory_id` **4519** (4518 returns zero events).
- O/U tabs: `DK_MLB_STAT_CATEGORIES` (`hits`, `total_bases`). Verify during a pregame slate:

```bash
python -m scripts.probe_dk_subcategories <event_id> --league mlb
```

Example event id from capture: `34267452`.

## Capture checklist (new markets)

1. **DK event id** — from game URL (`.../event/.../<id>`) or league slate `templateVars`.
2. **DK subCategoryIds** — DevTools → click prop tab → GET `.../event/eventSubcategory/v1/markets` → read `subCategoryId` in `marketsQuery` or `templateVars`.
3. **DK slate ids** — only if `./ev --league MLB` discovers zero events; capture league slate request `leagueId` + slate `subcategory_id`.
4. **Betr keys** — Proxyman `LeagueUpcomingEvents` for MLB; note projection `key` and `label` on a `SCHEDULED` event.
5. **Fixtures** — scrub tokens; save under `backend/tests/fixtures/` (`dk_markets_mlb_*.json`, `dk_league_mlb_events.json`, `betr_mlb_pregame.json`).

## Live props (future)

When live slates exist, add `--live` mode:

- Betr: `IN_PROGRESS` events, `isLive` projections, `current_value` as line, suspended/closed filtering.
- DK: `STARTED` events via `extract_event_ids(statuses=…)`.
