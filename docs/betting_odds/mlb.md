# MLB player props (Betr + DraftKings)

Pregame MLB props for the EV pipeline. **Live/in-game props are deferred** until Betr and DK offer them on the slate (see roadmap in `project_context.md` §6).

## v1 markets

| Canonical | Description |
|-----------|-------------|
| `h+r+rbi` | Hits + runs + RBIs O/U |
| `singles` | Singles O/U |

Other MLB props on the Betr board are ignored until a follow-up slice.

## Pipeline

```bash
cd backend
./ev --league MLB --skip-fd
```

- `--league MLB` drives Betr `LeagueUpcomingEvents` and DK slate key `mlb`.
- FanDuel is auto-skipped (no comparable MLB props).

## Betr

- League enum: `MLB` (confirm via GraphQL if capture differs).
- Pregame: `status == SCHEDULED`, `isLive == false`, `marketStatus == OPENED`.
- Record projection `key` / `label` for H+R+RBI and singles from a Proxyman capture, then update `BETR_MARKET_MAP` in `backend/config/market_maps.py`.

## DraftKings

- Slate: `DK_LEAGUE_SLATES["mlb"]` in `backend/config/dk_subcategories.py`.
- O/U tabs: `DK_MLB_STAT_CATEGORIES` (`h+r+rbi`, `singles`). Run probe during a pregame slate:

```bash
python -m scripts.probe_dk_subcategories <event_id> --league mlb
```

Replace `TBD` subCategoryId placeholders after probe.

## Live props (future)

When live slates exist, add `--live` mode:

- Betr: `IN_PROGRESS` events, `isLive` projections, `current_value` as line, suspended/closed filtering.
- DK: `STARTED` events via `extract_event_ids(statuses=…)`.
