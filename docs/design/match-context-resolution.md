# Match-context sharp resolution

## Goal

Replace post-hoc `event_start` side-index validation with a single canonical **match context** key
and **per-prop sharp filtering**, so DFS props only resolve against sharp lines from the same game
snapshot — eliminating ladder provenance drift (e.g. Freeman today vs tomorrow).

## Design decisions

- **Canonical key (`build_match_context_key`):** `player|market|league|[game]|[event_hour]|[live]`
  — line-agnostic; same components as `build_player_market_key` plus `event_hour = iso[:13]`
  (UTC hour-floor, e.g. `2026-06-19T17`). Reuses `normalize_player_name`, `normalize_game_key`,
  existing `is_live` suffix rules.

- **Per-prop resolution:** In `find_ev_opportunities`, for each Betr prop, **filter** DK/FD prop
  lists to rows where `build_match_context_key(sharp) == build_match_context_key(betr)` before
  building ladders or calling `resolve_sharp_quote`. No global sharp ladder across mismatched game
  times.

- **Missing `event_start` (pregame):** If Betr has `event_start` but no sharp row in the filtered
  pool → no match (`continue`). If Betr lacks `event_start` on a pregame row → skip (fail closed
  for MLB/WNBA/NBA pregame). **Live** rows (`is_live`): match on `player|market|league|game|live`
  only when Betr `event_start` is missing (clock unreliable in-game; game scope + live suffix
  already isolate).

- **Hour-floor tolerance:** Exact string equality on `event_hour` absorbs Betr/DK/API minute drift
  within the same start hour. Example: Betr `17:05`, DK `17:40` → both floor to `2026-06-19T17`
  → match.

- **Doubleheader disambiguation:** Game 1 vs Game 2 on the same calendar day have **different
  `event_hour`** values (MLB DH gaps are always >2 hours). Per-prop filtering naturally keeps
  Game 1 Betr props on Game 1 sharp lines only. No special DH logic beyond `event_hour` in the
  key.

- **Ladder provenance:** Store `event_start` on each O/U and milestone ladder row built from the
  filtered pool. Add `sharp_event_start: str | None` to `ResolvedSharpQuote`. Remove
  `_build_event_start_idx` and `_event_start_hour_mismatch` post-filter.

- **Interpolated / alt lines:** Resolution runs only on the filtered sharp pool, so bracketing
  rows for interpolation inherit the same `event_hour`. `sharp_event_start` on the quote comes
  from the ladder row used (exact, or nearest bracket for interpolated).

- **Multi-book:** Filter DK and FD independently by the same `build_match_context_key(betr)`
  before per-book resolve; consensus unchanged.

- **Collision logging:** Two sharp props sharing the same full key including `event_hour` and
  `line` → last-wins in ladder with `logger.warning` (data quality signal — should be rare once
  time is in the key).

- **FD `game` tagging:** Out of scope; until FD tags `game`, `event_hour` is the primary FD
  disambiguator for same-team slates.

## Doubleheader handling

Two distinct problems and why `event_hour` solves both:

| Scenario | Betr `event_start` | DK `event_start` | `event_hour` Betr | `event_hour` DK | Result |
|----------|-------------------|-----------------|------------------|----------------|--------|
| Same game, clock drift | `…T17:05Z` | `…T17:40Z` | `…T17` | `…T17` | Match |
| DH game 1 vs 2 | `…T17:05Z` | `…T23:10Z` | `…T17` | `…T23` | No match |
| Series (Freeman) | `…T02:10` (Jun 20) | `…T02:10` (Jun 21) | `…T02` (20th) | `…T02` (21st) | No match |

Per-prop filtering: Betr Game 1 only sees sharp rows with the same `event_hour`; Game 2 DK rows
never enter the ladder. No global collision, no side index required.

**Assumption:** MLB doubleheaders virtually always have >1 hour between first pitches. If two games
ever shared the same UTC hour (very unlikely), they would share a bucket — the same tradeoff as the
prior `betr-event-start-validation` approach. Hour-floor is the intentional choice over
minute-level keys.

## Non-goals

- Cross-book shared `event_id` matching (books use different ID schemes)
- Changing EV math, de-vig, milestone admission, or CLI output schema
- Sub-hour precision matching (minute-level keys) — hour-floor is sufficient and testable
- Reordering scrape output to prefer "today" over "tomorrow" in global ladders (per-prop filtering
  makes ordering irrelevant)

## Files / modules

- `backend/core/line_adjustment.py` — add `build_match_context_key`, `_hour_floor`; extend ladder
  row dicts with `event_start`; add `sharp_event_start` to `ResolvedSharpQuote`; populate on
  all resolve paths
- `backend/core/engine.py` — add `_filter_sharp_props_by_match_context(betr_prop, props)`;
  refactor `find_ev_opportunities` to filter-then-resolve per Betr prop; remove
  `_build_event_start_idx`, `_event_start_hour_mismatch`, `_hour_floor`
- `backend/tests/unit/test_ev_engine.py` — Freeman regression, DH game 1/2 separation, hour drift
  pass, missing `event_start` fail-closed pregame, live without `event_start` still matches with
  game+live scope
- `backend/tests/unit/test_match_keys.py` — unit tests for `build_match_context_key` collisions
  and DH hour separation
- `backend/tests/unit/test_line_adjustment.py` — ladder row carries `event_start`; resolved quote
  exposes `sharp_event_start`

## Behavior

- No new CLI flags
- `ev_opportunities.json` may gain optional `sharp_event_start` on rows (can stay on
  `ResolvedSharpQuote` only for debug in v1)
- Unmatched Betr props for "wrong date" sharp lines drop silently — same as prior debug-drop
  behavior, but earlier in the pipeline

## Test plan

- `cd backend && pytest -q`
- **Freeman / series:** Betr today + `[dk_today, dk_tomorrow]` same `game` → `[]`
- **DH game 1 pass:** Betr `17:05`, DK `17:40`, same `game` → match (minute drift, same hour)
- **DH game 1 vs game 2 block:** Betr game 1 (`17:05`), DK game 2 (`23:10`), same `game` +
  player + line → `[]`
- **Cross-day block:** mismatched `event_hour` on different calendar days → `[]`
- **Missing Betr `event_start` pregame:** sharp has time → no match (fail closed)
- **Live regression:** live Betr + pregame DK same `game` → `[]` (unchanged; `|live` suffix)
- **Multi-book:** DK today + FD tomorrow at same line → Betr today uses DK only (FD filtered out)
