# Line adjustment refactor — data-driven book registry

## Goal

Replace per-book hardcoded dispatch scattered across `line_adjustment.py` and `engine.py` with a
data-driven, book-registry approach so adding a 4th sharp book or a 2nd DFS app requires zero
edits to resolution or assembly logic.

## Problem

Book-specific logic was encoded in 7 locations:

**1. Flat per-book fields on `ResolvedSharpQuote`.** Every book had its own fields:
`dk_over_odds / dk_under_odds / dk_line_kind / dk_milestone_one_sided / dk_line_source` — and the
same six fields for FD and ESPN. Adding a 4th book = 9 new dataclass fields plus edits in 6 other
places.

**2. Per-book dispatch in 7 functions.** `_milestone_raw_book_odds`, `_book_quote_display_odds`,
and `resolve_book_sharp_quote` each had an `if book == "FanDuel": … elif book == "ESPN": … else:`
chain. `_assemble_multi_book_quote` hard-coded `dk_over, dk_under, fd_over, fd_under, espn_over,
espn_under` extraction. `_consensus_sharp_quote` hard-coded a DraftKings lookup.
`is_ev_eligible_quote` grew an `or`-chain per book.

**3. Semantic bug in `is_ev_eligible_quote`.** The gate triggered when *any* book's
`line_kind == "milestone"`. If DK priced a market via O/U and ESPN priced the same market via
milestone, the assembled quote had `adjustment_method="exact"` (DK O/U) but
`espn_line_kind="milestone"`, forcing the gate to require `dk_milestone_exact` — silently blocking
a valid DK O/U EV price. The `ou_ms_combo` workaround patched DK↔FD but was never extended to
ESPN. Not a live bug (ESPN milestone markets are disjoint from DK/FD O/U markets at time of
writing) but the structural guarantee breaks on the next book or market addition.

**4. DFS side hardcoded to Betr.** `find_ev_opportunities` referenced `BETR_STANDARD_BREAKEVEN_ODDS`
and the string `"Betr"` throughout. A second DFS app would require editing engine internals.

## Design decisions

### Data model

1. **`BookQuote` dataclass** (new, in `line_adjustment.py`):
   ```python
   @dataclass(frozen=True)
   class BookQuote:
       over_odds: int | None
       under_odds: int | None
       line_kind: LineKind          # "ou" | "milestone"
       line_source: str | None      # "exact", "dk_alt", "dk_milestone_exact", …
       milestone_one_sided: bool = False
   ```
   Replaces the per-book `{dk,fd,espn}_milestone_one_sided` flags and `{dk,fd,espn}_line_source`
   fields.

2. **`LineKind`** type alias (renamed from `DkLineKind`; same values). `DkLineKind` removed.

3. **`ResolvedSharpQuote` restructured:**
   - **Add:** `ev_line_kind: LineKind = "ou"` and `per_book: tuple[tuple[str, BookQuote], ...] = ()`
   - **Remove:** all 15 flat `{dk,fd,espn}_*` fields
   - **Keep unchanged:** `over_odds`, `under_odds`, `dk_line`, `betr_line`, `adjustment_method`,
     `corroborated`, `dk_main_line`, `sharp_books`, `milestone_admitted`, `milestone_devig_method`,
     `sharp_by_book`, `sharp_event_start`
   - **Add method:** `book_quote(self, book: str) -> BookQuote | None`

   Uses `tuple[tuple[str, BookQuote], ...]` (not `dict`) to keep the frozen dataclass hashable.

### Book registry

4. **`config/sharp_books.py`** (new):
   ```python
   @dataclass(frozen=True)
   class SharpBookConfig:
       name: str
       ev_priority: int                           # lower = preferred EV source
       ou_resolution: Literal["full", "exact_only"]
       # "full"       = DK  (exact + interpolate + extrapolate + milestone fallback)
       # "exact_only" = FD/ESPN (exact O/U only + milestone fallback; no interp/extrap)
       milestone_fallback: bool
       hold_own_book_only: bool
       # True  = use only own-book O/U hold for milestone devig (DK, FD)
       # False = prefer own-book O/U hold; fall back cross-book when absent (ESPN)

   SHARP_BOOKS: list[SharpBookConfig] = [
       SharpBookConfig("DraftKings", ev_priority=1, ou_resolution="full",       milestone_fallback=True, hold_own_book_only=True),
       SharpBookConfig("FanDuel",    ev_priority=2, ou_resolution="exact_only", milestone_fallback=True, hold_own_book_only=True),
       SharpBookConfig("ESPN",       ev_priority=3, ou_resolution="exact_only", milestone_fallback=True, hold_own_book_only=False),
   ]
   ```
   Adding a 4th book = one entry here, zero edits to `line_adjustment.py` or `engine.py`.

### EV eligibility fix

5. **`is_ev_eligible_quote` checks `ev_line_kind` only:**
   ```python
   def is_ev_eligible_quote(quote: ResolvedSharpQuote) -> bool:
       if quote.ev_line_kind == "milestone":
           return quote.adjustment_method == "dk_milestone_exact" and quote.milestone_admitted
       return quote.adjustment_method in EV_ELIGIBLE_ADJUSTMENT_METHODS
   ```
   A display-only milestone column from ESPN (or any future book) can no longer gate a DK O/U
   EV price.

6. **`ou_ms_combo` eliminated:** remove from `EV_ELIGIBLE_ADJUSTMENT_METHODS` and
   `_assemble_multi_book_quote`. With `ev_line_kind` tracked explicitly, DK O/U + FD/ESPN
   milestone display is naturally eligible without the workaround label.

### Dispatch elimination

7. **`_milestone_raw_book_odds` eliminated:** callers construct `BookQuote(...)` directly and
   append `(source_book, bq)` to `per_book`.

8. **`_book_quote_display_odds` eliminated:** `_assemble_multi_book_quote` iterates `per_book`
   directly.

9. **`resolve_book_sharp_quote` becomes strategy-driven:** replaces the `if/elif` per-book chain
   with a single code path parameterized by `cfg = SHARP_BOOK_BY_NAME[book]`. `cfg.ou_resolution`
   selects full vs exact-only resolution; `cfg.milestone_fallback` and `cfg.hold_own_book_only`
   drive the milestone path.

10. **`_assemble_multi_book_quote` generalized:** replaces hardcoded field extraction with a loop
    over `SHARP_BOOKS` in `ev_priority` order. Populates `per_book` from whichever books
    contributed a quote. Sets `ev_line_kind` from the winning quote's resolved line kind.

11. **`_consensus_sharp_quote` generalized:** replaces the hardcoded DraftKings lookup with a loop
    over `quotes`.

### Output stability

12. **Output JSON schema unchanged:** `_book_odds_from_resolved` in `engine.py` is rewritten to
    extract the flat `dk_over_odds / fd_over_odds / espn_over_odds` etc. keys by calling
    `resolved.book_quote(book)` for each book in `SHARP_BOOKS`. All existing output keys are
    preserved verbatim; no downstream consumers need changes.

### DFS-side abstraction

13. **`DFSSide` config** in `core/engine.py`:
    ```python
    @dataclass(frozen=True)
    class DFSSide:
        name: str
        breakeven_odds: int

    BETR = DFSSide(name="Betr", breakeven_odds=BETR_STANDARD_BREAKEVEN_ODDS)
    ```
    `find_ev_opportunities` gains `dfs_side: DFSSide = BETR` — backward compatible. A second DFS
    app (PrizePicks, Underdog) requires only a new `DFSSide` constant, no engine edits.

## Non-goals

- Output JSON schema changes (`dk_over_odds`, `espn_line_kind`, etc. keys are preserved)
- Actually adding a 4th sharp book or 2nd DFS app
- Parser, scraper, or fixture changes
- EV math changes (`calculate_ev`, `multiplicative_devig`, etc.)
- Ladder math changes (extrapolation, interpolation, devig functions)
- Renaming `adjustment_method` or `dk_line` in `ResolvedSharpQuote`

## Files / modules

- `backend/config/sharp_books.py` — NEW: `SharpBookConfig`, `SHARP_BOOKS`, `SHARP_BOOK_BY_NAME`
- `backend/core/line_adjustment.py` — add `BookQuote`, rename `DkLineKind → LineKind`, add
  `ev_line_kind` + `per_book` to `ResolvedSharpQuote`, add `book_quote()` method; eliminate
  `_milestone_raw_book_odds`, `_book_quote_display_odds`, `DkLineKind`; fix
  `is_ev_eligible_quote`; remove `ou_ms_combo`; generalize `resolve_book_sharp_quote`,
  `_assemble_multi_book_quote`, `_consensus_sharp_quote`
- `backend/core/engine.py` — add `DFSSide` + `BETR`; update `find_ev_opportunities` signature;
  rewrite `_book_odds_from_resolved` to read `per_book`; update `_append_side_opportunity` to use
  `dfs_side.name`; remove `DEFAULT_DFS_SPORTSBOOK`
- `backend/tests/unit/test_line_adjustment.py` — update direct `ResolvedSharpQuote(...)`
  constructions to use `per_book`; add `is_ev_eligible_quote` regression (DK O/U + ESPN milestone
  display → True)
- `backend/tests/unit/test_hits_total_bases_o05_equiv.py` — update any direct
  `ResolvedSharpQuote` constructions

## Behavior / flags

- No new CLI flags. No output schema changes.
- `find_ev_opportunities` and `compare_betr_vs_draftkings` gain optional
  `dfs_side: DFSSide = BETR` — backward compatible.
- `ou_ms_combo` no longer appears in `adjustment_method` output; props that previously emitted
  this label emit `"exact"` / `"dk_alt"` / etc. instead.

## Test plan

- `cd backend && pytest -q`
- **`is_ev_eligible_quote` semantic fix:** assemble a quote with `ev_line_kind="ou"` and
  `per_book=(("ESPN", BookQuote(line_kind="milestone", …)),)` — assert `is_ev_eligible_quote`
  returns True. (Regression: same scenario returned False before this fix.)
- **`ou_ms_combo` gone:** DK O/U + FD milestone scenario → `adjustment_method != "ou_ms_combo"`
  and `is_ev_eligible_quote` still True.
- **`per_book` populated correctly:** for a multi-book resolved quote, assert `book_quote()` for
  each book returns the correct `BookQuote` or `None`.
- **Output fields unchanged:** assert `_book_odds_from_resolved` still produces `dk_over_odds`,
  `fd_over_odds`, `espn_over_odds`, `dk_line_kind`, `espn_line_kind`, `dk_milestone_one_sided`,
  `dk_line_source` keys.
- **4th-book smoke test:** construct `SharpBookConfig("Pinnacle", ev_priority=4,
  ou_resolution="exact_only", milestone_fallback=False, hold_own_book_only=True)`, temporarily
  append to `SHARP_BOOKS`, pass a ladder to `resolve_multi_book_sharp_quote` — assert it resolves
  without any `if book == "Pinnacle"` guard in `line_adjustment.py`.
- **`DFSSide`:** call `find_ev_opportunities(…, dfs_side=DFSSide("PrizePicks", -120))` — assert
  `dfs_sportsbook` in all output rows is `"PrizePicks"`.
