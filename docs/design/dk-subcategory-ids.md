# DK subcategory ids: pregame labelling, derived reverse index, MLB milestone fill

## Context

`dk_api.py`'s market-label helper for logs and retry output hand-scanned three id maps out of a
registry that holds seven, so every MLB live id, every MLB pregame milestone id, and every WNBA id
logged as a bare integer. It went stale because each new id map was a second site someone had to
remember to edit alongside the scraper wiring.

Separately, six of those maps used a bare name (`STAT_CATEGORIES`) for their pregame state while
their live counterparts said `LIVE` explicitly, so reading the two side by side required knowing
which one was pregame. A pregame id pasted into a live probe already cost real debugging time,
since the pregame and live tabs use different subCategoryIds for the same market.

Finally, a new capture added 30 MLB subCategoryIds: 22 pregame milestone ids, 2 pregame O/U ids, 5
live pitcher milestone ids, and 1 live batter O/U id, plus two win-market ids that are recorded but
not wired.

## Design decisions

1. Keep the existing per-league, per-state, per-kind dict layout rather than moving to either a
   market-first grid or a row-per-id record table. The grid was rejected because today's maps are
   sparse by key and a grid would turn that sparsity into explicit nulls. The record table is
   stronger on traceability (a verified-on date per id) but the per-id upkeep delta against the
   current layout collapses to about the same once the reverse index below is derived instead of
   hand-listed, so the larger refactor wasn't justified mid-feature.

2. Rename the six pregame-state constants to say `PREGAME` explicitly
   (`DK_{NBA,WNBA,MLB}_STAT_CATEGORIES` becomes `DK_*_PREGAME_STAT_CATEGORIES`, and similarly for
   the milestone maps). State is the axis that silently produces a wrong-but-well-formed request, so
   an unmarked default is exactly how a pregame id ends up probed against a live event.

3. Derive the id-to-market reverse index used for logging by walking the registry itself instead of
   hand-listing each map. The registry already enumerates every map per league per state, so the
   walk is exhaustive by construction and needs no second edit when a league or map is added.

4. The mismatch warning for a milestone label now names the resolved tab, not a hardcoded constant
   name, so it stays correct when it fires for a league the message wasn't written for.

5. New combo market keys join abbreviated stat names with `+` (`xbh`, `h+r+sb`, `h+sb`, `h+bb+sb`,
   `r+rbi`), matching the existing `h+r+rbi` and `h+bb+er` precedent.

6. Retire the standalone discovery manifest for MLB. Every id block it carried duplicated either the
   subcategory registry or the sportsbook docs, and the one piece of unique content (a note on
   milestone tab pricing) moved into the sportsbook doc. Nothing in the pipeline read the file.

7. Ids that are captured but not wired live in the sportsbook doc's reference table, not in the
   registry's placeholder slot, since that slot already has a different meaning (a market the other
   side has and DK doesn't, rather than the reverse).

8. The pitcher win market is recorded as reference only. DK posts it as a two-sided tab, but it has
   no numeric line, and the O/U and milestone parsers both key on a line, so wiring it needs new
   parsing and pricing logic outside this scope.

9. Only `N+`-style milestone tabs are wired. DK's pitcher milestone tabs other than strikeouts use
   an "X or Fewer" label the parser doesn't recognize, and it fails silently: the tab fetches fine
   and contributes zero rows rather than raising. Supporting that format needs a sided
   threshold-to-line mapping and an under-side path in the pricing math, which is its own
   follow-up.

10. No id is written to the registry before a live probe confirms it responds with markets,
    including ids that had been sitting in the retired discovery manifest since before the
    pregame/live split existed.

## Non-goals

- The market-first grid and the row-per-id record table (decision 1).
- Wiring the pitcher win market as a canonical key (decision 8).
- NBA live O/U and milestone capture, blocked on catching an NBA game mid-game to read ids off
  live network traffic (see *WNBA capture addendum* below); the engine needs no changes since it
  is already league-generic.

## WNBA capture addendum (2026-08-04)

WNBA pregame and live O/U and milestone ids, verified against live WNBA events. The prior identity
alias (`DK_WNBA_*_STAT_CATEGORIES = DK_NBA_*_STAT_CATEGORIES`) held only by accident, and only for
one axis:

- **Pregame O/U ids match NBA's exactly** for every market WNBA carries, so the alias is kept
  (filtered to drop `steals`/`blocks`/`stl+blk`, confirmed absent from the WNBA board rather than
  merely unprobed. A full alias would have requested tabs WNBA doesn't post and gotten back
  empty markets, the same failure class as a stale id).
- **Pregame and live milestone ids do not match NBA's** (e.g. WNBA points milestone `16477` vs
  NBA's `2716477`), so `DK_WNBA_PREGAME_MILESTONE_STAT_CATEGORIES` and the new
  `DK_WNBA_LIVE_MILESTONE_STAT_CATEGORIES` are standalone dicts, not aliases.
- **Live O/U** (`DK_WNBA_LIVE_STAT_CATEGORIES`) is new and standalone; `reb+ast` wasn't caught live
  in this capture and stays `None` (pending) until a future game.
- **Double-double / triple-double** are confirmed for WNBA in both pregame and live, and
  deliberately **not** wired. DraftKings quotes them as a single `Yes` selection with no numeric
  threshold, which `_parse_milestone_threshold` cannot read, so the tab fetches cleanly and yields
  zero rows. The ids are recorded in `docs/betting_odds/draftkings.md` instead, the same handling
  the "X or Fewer" pitcher tabs get, and a guard fails if one is wired back without the parser and
  pricing work behind it. NBA's equivalents remain unprobed (`DK_NBA_PENDING_STAT_CATEGORIES`).

  Recording rather than wiring is the deliberate call: a wired id that yields nothing is
  indistinguishable at runtime from a market the book has not posted yet, so it would read as
  working coverage. The blocker is also not only parsing. A binary market is one ladder rung, and
  `devig_milestone_fair_over` normalizes across a segment of at least two, so enabling these means
  choosing how to de-vig a single-rung longshot that has no over/under rows to estimate a hold
  from. That is a pricing decision with its own evidence requirements, not a config change.

This settles the open question from the original decision log about whether WNBA needed a
shared-pool-with-membership structure once market divergence was confirmed: it didn't, because the
divergence turned out to be per-axis (O/U aliases, milestone doesn't) rather than per-market, so
each axis just picks the simpler of alias-or-own-dict independently.

## Files / modules

- `config/dk_subcategories.py`: renamed pregame constants; derived reverse index; filled the MLB
  pregame milestone map and added the confirmed MLB pregame and live O/U ids.
- `scrapers/sportsbooks/dk_api.py`: market-label helper delegates to the derived index; label
  patterns for the new combo markets, ordered so a combo pattern is checked before the single-stat
  patterns it could false-match.
- `core/ev_display.py`: abbreviations for the new combo market keys.
- `docs/betting_odds/draftkings.md`, `docs/betting_odds/mlb.md`: id tables, renamed constants, and
  a new reference table for captured-but-unwired ids.
- Deleted: `config/discovery/mlb.yaml` and its directory.

## Test plan

- A registry-wide guard asserts every configured subcategory id in the registry can be labeled,
  independent of the module's own index-building walk.
- A guard asserts each label matches the state and kind of the tab it was read from.
- A guard asserts no id maps to two different (state, kind, market) meanings; WNBA's pregame O/U
  alias to NBA's ids passes this unaided, since an aliased id keeps the same (state, kind, market)
  meaning in both leagues rather than colliding on a different one.
- Existing tests for the renamed constants and the previously-empty MLB pregame milestone map were
  updated to match; the milestone map used to assert empty as a statement of capture status, not a
  design invariant.
- Label-pattern coverage for each new combo key, including a case where the combo label contains
  another market's single-stat wording.
