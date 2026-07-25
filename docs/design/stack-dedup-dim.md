# Stack column: unconditional team marker, per-player dim, confidence mute

## Context

The Stack column answers one question: is this player part of a same-team cluster? That is a
property of the player, not of the row. The original implementation made it row-conditional.
Within a `(league, team)` group holding at least two distinct players, only each player's
best-EV row got the marker and the cluster colour; every other row of that team rendered blank.

That cost two things:

1. **The column did not mean what its header implied.** Reading a one-glyph column required
   learning a second rule (`marker = same team AND best prop for this player`), and a team
   fragmented into a scatter of marks instead of one bar.
2. **The dedup signal was destroyed rather than de-emphasised.** A blank Stack cell was
   indistinguishable from "not in a cluster at all".

Splitting the two concerns gives each channel exactly one fact: marker means team membership,
dim means per-player redundancy.

A related credibility problem shared the same surface. Rows priced from a one-sided milestone
carry an EV that is estimated rather than observed, because no two-sided quote existed from any
sharp book, and there is no cross-book de-vig consensus even when a second book corroborates.
The EV tier colour presented those rows with exactly the same confidence as a real exact quote.

## Design decisions

1. **The marker is unconditional within a cluster.** Every row whose `(league, team)` group
   holds at least two distinct players gets the marker at full cluster colour. The
   two-distinct-players qualification is unchanged: a lone player with many props still gets
   no marker.

2. **Dim marks each player's non-best rows, independent of clusters.** The grouping key is
   `player` alone over the whole row list, not re-scoped to `(league, team)`, because a lone
   player's rows sit outside any team grouping. This is the same identity assumption the
   cluster grouping already relies on; no player ID exists anywhere in the pipeline to key on
   instead.

3. **"Best" is selected per trust tier, not once per player.** Up to two rows stay bright: the
   best-EV exact row and the best-EV milestone row, chosen independently, where
   `is_exact = line_source != "milestone_exact"`. Within-tier ties break by EV, then by first
   row.

   The rejected alternative was a single lexicographic `(is_exact, ev)` winner. Selection is
   scoped to the rows actually on the table, and no minimum-EV gate is applied on the display
   path, so a marginal exact can sit beside a strongly priced milestone for the same player.
   Under tier-first ordering that weak exact would take the single bright slot on tier alone
   and dim the stronger milestone, which is the mirror image of the problem being fixed. Giving
   each tier its own slot kills both directions at once, with no magnitude threshold and no
   arbitrary constant, because the split reuses the same exact-versus-milestone distinction the
   rest of the design already rests on.

   The accepted consequence: a mixed-tier player can show two bright rows. They read as
   tier-labeled rather than equally confident, because a bright milestone row is necessarily
   also grey.

4. **Adjusted lines share the exact tier, by definition rather than oversight.** Interpolated
   rows compete with real exact quotes for one bright slot and are not muted. The mute trigger
   is specifically "no two-sided quote existed at all"; adjusted rows do have a two-sided quote,
   interpolated across lines, which is a categorically smaller uncertainty. Muting both would
   collapse two different data-quality signals into one grey.

5. **Confidence mute is colour substitution, not a dim.** On a milestone row the three
   credibility cells (Hit%, EV%, Src) are substituted with a flat grey. Applying the dim escape
   or a luminance dim to EV% would collide with the tier ramp, which already encodes magnitude
   in luminance: a dimmed bright green could read as a lower tier. Grey sits off the
   green-to-red hue axis, so "estimated" reads as a channel distinct from "how large".

6. **The milestone glyph is a text-presentation diamond, not the emoji.** The emoji ignored
   foreground colour on most terminals, which made the mute unrenderable on the one cell that
   most needed it. Only the character changed; no escape codes are embedded in the
   value-formatting functions.

7. **A column registry replaces positional layout knowledge.** One ordered tuple owns column
   order, headers, widths, and declarative style roles (cluster swatch, EV tier, credibility,
   soft glyph, and the Stack column's exemption from dim). Cell values are built
   once by key and arranged through the registry, so a mismatch raises rather than silently
   shifting a column. Callers and tests address columns through a `column_index()` accessor
   instead of re-declaring index constants.

8. **Styling composes rather than selects.** A single annotate pass produces one `RowStyle` per
   row, replacing the parallel marker and colour lists indexed by row position. A single styling
   pass builds every escape sequence. Highlight beating dim is resolved during annotation, so
   the styling pass never receives both.

9. **Glyph grey is scoped to the glyph.** In an odds cell, only the diamond takes the mute grey;
   the odds value beside it keeps the row's own styling. Because SGR attributes accumulate,
   restoring the surrounding style requires an explicit reset before re-opening the base codes.
   Re-applying the base codes alone leaves the grey foreground in effect for the rest of the
   cell.

## Non-goals

- Per-book display tiers. Milestone rows are greyed uniformly. If per-book milestone pricing
  proves to differ in quality, that belongs in the pricing math, not in a display tier.
- A desaturated tier bank as an alternative to the dim escape. Held in reserve; it returns only
  if the dim proves illegible on a real terminal.
- Pipeline-level collapse of both legs of a two-way market. That is a separate layer with no
  shared surface.

## Files / modules

- `backend/core/ev_display.py`: column registry, `RowStyle`, marker and dim computation, the
  SGR styling pass, glyph swap.
- `backend/tests/unit/test_ev_display.py`: rewritten cluster and dedup guards, new layer
  interaction matrix.
- `backend/tests/unit/test_milestone_ev_board.py`: updated for the removed `marker=` argument
  on `format_ev_opportunity_row`.

The sole production caller, `backend/core/ev_pipeline.py`, is unchanged. The public signature of
`format_ev_opportunities_table` is unchanged. `format_ev_opportunity_row` drops its `marker=`
argument, which predated the cluster pass and is superseded by the registry.

## Test plan

- Guards for each layer: unconditional marker, per-player dim outside a cluster, per-tier bright
  selection, within-tier dimming, highlight beating dim, Stack exemption from dim, a clustered
  Stack cell keeping its swatch colour under highlight, mute firing only on milestone rows, mute
  remaining independently detectable from dim, bold plus grey never becoming bold plus tier,
  glyph substitution, and glyph grey not bleeding past the glyph.
- A parametrized matrix over dim, highlight, cluster, and milestone so a failure names the
  offending combination.
- The milestone Src label and the soft-odds sample are derived from the formatters under test
  rather than restated, so a future glyph change cannot leave an assertion silently checking the
  old character.
- The plain path and the table header stay free of escape sequences.
- Column positions are addressed through `column_index()` or by header name, never by literal
  index.
