# Milestone (over-only) props on the +EV board

## Context

Milestone props (DK `N+`, over-only) could never reach the +EV board. `is_ev_eligible_quote`
required `dk_line_kind == "ou"`, and the milestone fair-prob path took the **raw implied** of the
one-sided over price — vig-inflated and deliberately conservative. A `-200` `1+ hits` prop would
be dropped at the eligibility filter even if it was genuinely sharp.

Two gaps motivated this change:

1. **No de-vig for milestones.** A lone `N+` price still carries house hold, but with no opposite
   side we can't strip it symmetrically. However, DK's `N+` prices form a **survival curve**
   `S(N)=P(X≥N)`. A contiguous ladder lets us renormalize the vig-inflated increments; a lone
   threshold can still be hold-estimated from sibling O/U markets.

2. **No path onto the board.** Sufficiently sharp milestone overs should be rankable, gated by a
   price-quality bar computed from observed market hold rather than an arbitrary constant.

### Book coverage

DraftKings and FanDuel both emit MLB milestones (one-sided `N+` and two-sided Yes/No
runners). The de-vig and gate logic lives in the **book-agnostic** layer (`core/line_adjustment.py` /
`core/engine.py`, keyed off `line_kind`/`line`/`milestone_threshold`, not DK-specific fields) so
any future book that starts emitting `line_kind == "milestone"` props flows through automatically.
Three concrete places to avoid DK-only coupling:

- **Ladder source:** `build_milestone_ladder` is fed the union of all sharp-book props carrying
  `line_kind == "milestone"`, not just the DK list.
- **Provenance:** milestone quotes set `sharp_books=(source_book,)` so the board shows the actual
  origin book.
- **Hold estimate:** `estimate_ou_hold` prefers the source book's own O/U ladder, then falls back
  cross-book, then `MILESTONE_ASSUMED_HOLD`.

## Design decisions

1. **De-vig method:** ladder-normalization when a contiguous `N+` ladder exists; hold-shrink
   fallback for a lone threshold.

2. **Eligible resolutions:** only `milestone_exact` (threshold sits exactly at the Betr line).
   Interpolated/extrapolated milestones stay off the board.

3. **Price gate:** dynamic — strip vig using the **observed O/U hold** for the same
   league/market, with a static `MILESTONE_ASSUMED_HOLD` fallback. Admission floor
   `MILESTONE_MIN_FAIR_OVER` defaults to `−160` → `0.6154`.

4. **Gate target:** test the **post-de-vig fair over** (the number we'd bet against), not the
   raw price.

5. **Precedence:** unchanged — de-viggable O/U (DK or FD) always wins; milestone remains a
   strict gap-filler.

6. **Surfacing:** every admitted milestone +EV row is flagged as one-sided / not-true-devig. Add
   `milestone_devig_method`, `milestone_admitted`, and `not_true_devig: true` to JSON rows; add
   a `Src` badge (`ms🔶`) in the CLI table to visually distinguish milestone rows from true-devig
   rows.

7. **Tunables:** `config/settings.py` constants with env overrides, mirroring the
   `SHARP_BOOK_WEIGHTS_*` / `_float_env` pattern.

## Non-goals

- No change to O/U or multi-book-consensus resolution, weighting, or precedence
- No interpolated/extrapolated milestone admission
- Milestone overs do not feed multi-book consensus
- No new scrape fields; reuse the milestone ladder already built from sharp props

## Files / modules

### `config/settings.py`
```python
MILESTONE_MIN_FAIR_OVER = _float_env("MILESTONE_MIN_FAIR_OVER", 0.6154)  # −160
MILESTONE_ASSUMED_HOLD  = _float_env("MILESTONE_ASSUMED_HOLD", 0.06)     # fallback two-sided hold
```

### `core/line_adjustment.py`

- **`estimate_ou_hold(ou_ladders, pm_key) -> float | None`**: averages two-sided hold
  `implied(over)+implied(under)−1` across that player|market's O/U rows. Prefers the source
  book's O/U ladder; falls back cross-book; returns `None` with no O/U rows anywhere.

- **`devig_milestone_fair_over(lines, target_line, *, market, ou_hold) -> tuple[float, str]`**:
  - *Ladder-normalization* (≥2 contiguous thresholds around target): convert raw implied survival
    values `s_i = american_to_implied(over_i)` to PMF masses, renormalize to sum to 1, rebuild
    fair `S(target)`. Returns `(fair_over, "ladder_normalized")`.
  - *Hold-shrink fallback* (lone/non-contiguous threshold):
    `fair_over = s_target * (1 − h/2)` where `h = ou_hold ?? MILESTONE_ASSUMED_HOLD`.
    Returns `(fair_over, "hold_shrink")`.

- **`_resolve_milestone_ladder`**: thread O/U ladders in so it can call `estimate_ou_hold`. For
  the `dk_milestone_exact` branch, compute `fair_over, devig_method`, gate against
  `MILESTONE_MIN_FAIR_OVER`, set `milestone_admitted`, `milestone_devig_method`, and
  `sharp_books=(source_book,)`.

- **`is_ev_eligible_quote`**: extend to admit milestone:
  ```python
  if quote.dk_line_kind == "milestone":
      return quote.adjustment_method == "dk_milestone_exact" and quote.milestone_admitted
  return quote.adjustment_method in EV_ELIGIBLE_ADJUSTMENT_METHODS
  ```

### `core/engine.py`

- **Milestone ladder feed:** build from the union of all sharp-book props carrying
  `line_kind == "milestone"` — not just the DK list.
- **`_fair_probs_from_resolved`:** for milestone, use the stored de-vigged fair over instead of
  raw `american_to_implied(resolved.over_odds)`.
- **`_append_side_opportunity`:** add `milestone_devig_method`, `milestone_admitted`, and
  `not_true_devig` fields to the row dict.

### `core/ev_display.py`

- Extend `_LINE_SOURCE_DISPLAY` so admitted milestone rows render with `ms🔶` in the `Src`
  column — distinguishing one-sided milestone +EV from true-devig rows without adding a column.

## Test plan

New fixture: `tests/fixtures/dk_milestone_ladder.json` — contiguous DK `N+` ladder for one
player|market, a lone-threshold case, and a sibling O/U market for hold estimation.

Unit tests:

- `estimate_ou_hold` returns sane positive hold; `None` with no O/U rows
- `devig_milestone_fair_over` ladder-normalization lowers fair over below raw implied and returns
  `"ladder_normalized"`; lone threshold returns `"hold_shrink"` using observed hold then the
  static fallback
- Gate boundary: fair over just above/below `MILESTONE_MIN_FAIR_OVER` flips `milestone_admitted`
- `is_ev_eligible_quote`: `dk_milestone_exact` + admitted → True; interpolated/extrapolated
  milestone → False regardless of price
- Precedence regression: a player with both O/U and milestone resolves via O/U; milestone
  untouched
- Engine integration: admitted milestone yields a board row carrying `milestone_admitted=True`,
  `milestone_devig_method`, `not_true_devig=True`, and the `ms🔶` `Src` badge
- Book-agnostic: an admitted milestone quote sets `sharp_books` to its source book; a synthetic
  non-DK milestone prop resolves through the same path and is attributed to that book
