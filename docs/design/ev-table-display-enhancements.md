# EV table display enhancements — highlight hook, same-team marker, EV coloring

## Context

The timed loop previously re-implemented header/separator/row rendering inline solely to wrap
"new this run" rows in bold yellow. That duplication was the primary maintenance risk.
Both `./ev` and `./loop` now share one formatter with EV-tier and stack coloring enabled.

Separately, a displayed board can contain multiple players from the same team ranked non-adjacently
by EV — relevant for same-team parlay construction, where each player can appear at most once.
A single player's multiple props do not indicate parlay clustering (obvious from the Player column
and not parlayable against itself). Cross-league team-abbreviation collisions (e.g. MIN → Twins
and Lynx) require grouping on `(league, team)`, not abbreviation alone.

Finally, most non-live runs cluster near 0% EV while live MLB edges often sit in a narrow low-positive
band — tier boundaries are denser on the low-positive end so the best plays stand out at a glance.

## Design decisions

1. **Reusable highlight hook on the real formatter.** `format_ev_opportunities_table` accepts an
   optional `highlight: Callable[[dict], bool] | None`. When true for a row, each cell's padded
   text is wrapped in bold yellow (`\033[1;33m`) before joining — not the fully-joined row string.
   Per-cell wrapping prevents ANSI reset clashes when other per-cell styling is added on the same
   row. `./ev` passes no `highlight` kwarg; `./loop` passes
   `highlight=lambda p: prop_key(p) not in seen` (notified-set state stays in the loop).

2. **Same-team parlay cluster marker (`Stack` column).** Sits between `Lg` and `Game`, so the
   per-team tint reads adjacent to the player name it groups. Computed once
   per `format_ev_opportunities_table` call over its `rows` argument (already the displayed,
   top-`n`-truncated board upstream). Algorithm:
   - Group rows by `(league, team)`; skip rows with no `team`.
   - A group is "clustered" only when it has ≥2 **distinct players**.
   - Within a clustered group, for each distinct player, mark **only their single highest-`ev` row**
     (raw `ev`, not rounded `ev_pct`; ties break to first in the EV-sorted input list).
   - Glyph `▌` on marked rows, blank otherwise. EV rank ordering is never re-sorted to cluster teams.

3. **EV-magnitude coloring on the EV% cell only.** Enabled via `color_ev=True` on
   `format_ev_opportunities_table` / `format_ev_opportunity_row` (on for `./ev` and `./loop`).
   Uses xterm-256 (`\033[38;5;{n}m`) with seven tiers
   (denser on low-positive EV, red tiers for negative):

   | Tier | Range | Code |
   |---|---|---|
   | bright green | `ev_pct >= 5.0` | 46 |
   | green | `3.0 <= ev_pct < 5.0` | 40 |
   | light green | `1.5 <= ev_pct < 3.0` | 34 |
   | lightest green | `0.0 <= ev_pct < 1.5` | 28 |
   | lightest red | `-1.0 <= ev_pct < 0.0` | 217 |
   | light red | `-2.0 <= ev_pct < -1.0` | 210 |
   | red | `ev_pct < -2.0` | 196 |

   When a row is both highlighted and tier-colored, the EV% cell uses a single combined escape
   (`\033[1;38;5;{n}m`) so neither style's reset truncates the other; remaining cells keep
   bold-yellow only. Missing `ev_pct` (defensive test fixtures only) stays plain/uncolored.

4. **Display polish (follow-up).** Three refinements from visual review:
   - **Brightness ramp for positive EV greens.** The original saturation-based ramp was
     non-monotonic in perceived brightness (mid-tier greens looked dimmer than higher tiers).
     Positive tiers now use pure-green xterm codes 46/40/34/28 with brightness descending as
     EV falls; red tiers and all boundaries are unchanged.
   - **`Grp` renamed to `Stack`.** The column marks same-team parlay stacks, not generic
     grouping; width increased from 3 to 5 so the header is not ellipsized.
   - **Per-cluster marker coloring.** The `▌` glyph is tinted from a
     six-color bank `[33, 208, 51, 201, 99, 30]` assigned in first-appearance order down
     the board (cycling if clusters exceed the bank). Keyed on `(league, team)` like the
     marker itself. The Stack cell is exempt from bold-yellow "new row" highlight so team
     color is never clobbered.

## Non-goals

- No re-sorting or re-grouping rows by team.
- No team-color swatch in the terminal table beyond per-board cluster tinting on the Stack
  column (color data may be reused elsewhere later).
- No new `./ev` CLI flags for toggling color.
- No EV scan, ranking, or engine math changes.

## Files / modules

- `backend/core/ev_display.py` — `format_ev_opportunities_table`, `format_ev_opportunity_row`,
  `EV_TABLE_HEADERS`, `EV_TABLE_WIDTHS`, cluster-marker and tier-color helpers.
- `backend/core/ev_pipeline.py` — ranked table log uses `color_ev=True`.
- `loop` — all leagues, no default `--min-ev`; `format_ev_opportunities_table` with
  highlight + `color_ev=True`.
- `backend/tests/unit/test_ev_display.py` — highlight, marker algorithm, tier boundaries, combined
  ANSI composition.

## Test plan

- Formatter default (`color_ev=False`) stays plain for unit tests; `./ev` and `./loop` enable color.
- Highlight wraps each cell independently; combined highlight + tier on EV% cell preserves highlight
  on columns after EV%.
- Marker: best-prop-per-player only; lone multi-prop player unmarked; cross-league abbrev pairs
  do not cross-mark; `ev` ties favor first input row.
- Each tier boundary maps to the locked xterm-256 code.
