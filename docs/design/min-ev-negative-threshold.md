# `--min-ev` becomes a real inclusive threshold

## Context

`--min-ev` defaulted to the float `0.0`, which was forced to do double duty: it meant both "the
user explicitly wants strictly-positive EV" and "the user typed nothing, don't filter at all."
Those two intents collided on one value, with two symptoms:

- `--min-ev -0.05` (a real use case — "show me anything better than -5% when nothing's +EV") made
  the filter gate (`plus_ev_only or min_ev > 0`) evaluate `False`. Filtering silently disabled
  itself instead of applying; the full board dumped regardless of the threshold requested.
- `row["plus_ev"]` was computed as `ev > min_ev` — coupled to whatever threshold was passed — so a
  row could carry `plus_ev: True` while its actual `ev` was negative (e.g. `--min-ev -0.05` with
  `ev=-0.03` set `plus_ev=True`). `plus_ev` is meant to mean "genuinely positive EV," which by
  definition excludes zero and anything below it; a threshold-dependent `plus_ev` is wrong
  independent of the filtering bug above.

`--plus-ev-only` existed solely to route around the ambiguity — confirmed to have zero other
consumers and zero test coverage anywhere in the codebase, i.e. it existed only to force this one
gate.

A deeper issue sat beneath the CLI-level fix: `filter_min_ev: bool` was threaded alongside
`min_ev: float` as two independent parameters through four function signatures
(`run_refresh` → `run_ev_scan` → `compare_betr_vs_draftkings` → `find_ev_opportunities`), only
the last of which actually read either value — the middle two were pure pass-through. Any future
direct caller of `find_ev_opportunities(props, dk, min_ev=0.02)` who forgot `filter_min_ev=True`
would reproduce the same bug class at a new call site, with nothing in the signature to prevent
it.

## Design decisions

1. **Single `float | None` sentinel, not a float+bool pair.** `min_ev` collapses to one
   `float | None = None` parameter, threaded unchanged through all four layers in the call chain.
   `None` means "omitted, unfiltered"; any float (positive, negative, or zero) is an explicit,
   always-applied threshold. `filter_min_ev` is deleted at every layer — the three outer layers
   were already pure pass-through, so removing the second parameter is strictly less surface, not
   more.

2. **The threshold is inclusive.** The one place in the chain that actually branches on the
   sentinel (`find_ev_opportunities`) filters with `if min_ev is not None: rows with
   ev >= min_ev`, replacing the old `if filter_min_ev: rows with plus_ev`. This makes `--min-ev`
   self-sufficient for any threshold a user wants, including exactly `0`, without a companion
   flag.

3. **`plus_ev` is decoupled from the threshold.** `plus_ev` becomes the literal, unconditional
   `ev > 0`, independent of whatever `--min-ev` was passed. `--min-ev` is now purely an output
   filter on the raw `ev` value; `plus_ev` is purely a fact about the row. This is a real,
   independent correctness fix riding along with the threshold fix — the two were entangled by
   the same coupling and required the same decoupling to resolve. `plus_ev` itself is not
   removed: it remains a precomputed per-row boolean, since it's a live consumer for the output
   schema (asserted in the regression suite and golden snapshot), a downstream milestone-caveat
   warning flag, and run-summary logging (`top=N plus_ev=M`) — all three become honest
   automatically once the computation itself is fixed, with no changes needed at those call
   sites.

4. **`--plus-ev-only` is removed entirely,** not deprecated — flag, parameter, and call site.
   It becomes fully redundant once `--min-ev 0` alone means "strictly positive" without it, and
   it had no other consumers to preserve compatibility for.

5. **The downstream `loop` runner's implicit `--min-ev 0.02` injection is removed.** Once
   omitting `--min-ev` means "full board" for the underlying tool, a wrapper that silently
   injected a 2% floor when the flag was omitted became an inconsistency in the same direction as
   the bug being fixed. Omitting `--min-ev` now shows the full (still `--top-n`-capped) board on
   every iteration and alerts on any new top-`n` entrant, not just threshold-qualifying ones —
   a real, intentional UX change, not just a wording fix. Users who want the old
   alert-above-a-threshold behavior pass `--min-ev` explicitly, same as before, just no longer
   implicit.

## Non-goals

- No change to how `ev` / `ev_pct` are computed — this is a filter/flag-semantics fix, not a math
  change.
- No change to `--top-n` behavior or default — orthogonal, untouched. "Full board" throughout
  this fix means "not EV-filtered, still capped to `--top-n`," not literally unbounded.
- No display/formatting changes — unrelated to table rendering.

## Files / modules

- `core/pipeline_runner.py` — `--min-ev` default (`None`) and help text; `run_refresh` signature;
  `--plus-ev-only` removal (flag + parameter + call site).
- `core/ev_pipeline.py` — `run_ev_scan` signature: `filter_min_ev` dropped, pure pass-through
  otherwise.
- `core/engine.py` — `compare_betr_vs_draftkings` signature collapse; `find_ev_opportunities`'s
  filter logic; `_append_side_opportunity`'s `plus_ev` computation decoupled from `min_ev`.
- Downstream `loop` runner — injection block and its tracking variable removed; help text updated.

## Test plan

- Threshold test rewritten to cover: unfiltered (`min_ev=None`), a threshold that excludes all
  rows, and a threshold that keeps qualifying rows.
- New coverage for filtering at a negative threshold, confirming a row with small negative EV is
  correctly excluded when the threshold sits above it and included when the threshold sits below
  it.
- New CLI-parse coverage: `--min-ev` omitted parses to `None`; negative, zero, and positive
  values all parse to the matching float.
- ~30 now-dead `min_ev=0.0` keyword arguments removed from existing call sites across the test
  suite — each one only existed to satisfy the old required-argument shape and asserted nothing
  about the value itself, confirmed by reading each site before removing it.
- Full unit suite otherwise unaffected — no scraping, matching, or ranking behavior changed.
