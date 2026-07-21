# Consensus fair-probability precision loss

## Context

Two MLB total-bases props on the same line, same market, same game, showed byte-identical
`EV%` and `Hit%` despite DraftKings quoting genuinely different odds for each side
(-165/+125 vs -170/+125). Both were multi-book consensus rows (2+ sharp books quoting the
same exact O/U line), and the collapse traced to two stacked rounding round-trips:

1. The consensus fair probability is computed by weight-averaging each contributing book's
   de-vigged fair probability, then normalizing the over/under pair to sum to 1. This
   produces an accurate float per row.
2. That float is immediately converted to whole-cent American odds for display. Two floats
   close enough together (as in this case) can round to the identical integer price, and the
   float itself is then discarded.
3. `ResolvedSharpQuote` only stored the resulting integer odds, with nowhere to carry the
   float from step 1. The EV computation, when handling a consensus row, re-derived the fair
   probability from those already-rounded odds instead of using the original average,
   collapsing both rows to the same probability, and therefore the same EV.

The consensus quote is assembled in two places: the function that computes the weighted
average, and its only caller, which builds a second, fresh copy of the quote from a subset
of the first one's fields. A fix that only touched the first site would have been a silent
no-op, since the second, unmodified copy is what the EV computation actually receives.

## Design decisions

1. **Carry the float alongside the odds, not instead of them.** `ResolvedSharpQuote` gains
   two optional fields, `fair_over` and `fair_under`, populated only on the consensus path.
   The existing integer `over_odds`/`under_odds` fields are unchanged and still drive display;
   nothing currently rendered reads the consensus-level odds directly, so the fix is additive
   with no display-side change.

2. **The floats are the normalized probabilities**, i.e. the same over/under pair, already
   summing to 1, that gets fed into the odds-rounding step. Populating a pre-normalization
   value would introduce a second, inconsistent probability pair on the same object.

3. **Both consensus-quote construction sites populate the new fields.** The averaging
   function sets them on the quote it returns; its caller, which builds a second quote object
   from that result, copies them across explicitly. Missing the second site would have left
   the fix inert, since that is the object the EV path actually consumes.

4. **The EV computation stops re-deriving probability from odds for consensus rows.** It now
   asserts the two float fields are present (a precondition, not a fallback: their absence
   on this code path is a programming error) and returns them directly, with no
   re-normalization. Every other adjustment method's EV computation is untouched.

## Non-goals

- A universal float-carrying quote for every adjustment method (milestone, single-book O/U,
  interpolated/extrapolated lines). This fix is scoped to the multi-book consensus path only;
  broadening it to every method changes a contract the rest of the codebase depends on and is
  a separate, larger change.
- Any change to the de-vigging method itself.
- Any change to per-book display columns or odds formatting: confirmed nothing currently
  renders the consensus-level integer odds directly.
- Per-book weight tuning for the consensus average.

## Files / modules

- `core/line_adjustment.py`: `ResolvedSharpQuote` dataclass, two new optional float fields.
- `core/multi_book_resolver.py`: the function that computes the weighted consensus average,
  and the wrapper that assembles the quote the EV path actually receives; both populate the
  new fields.
- `core/engine.py`: the EV computation's consensus branch, returns the carried floats
  directly instead of re-deriving them from rounded odds.

## Test plan

- Regression test reproducing the original two-prop collapse: same odds that previously
  produced identical fair probabilities now produce distinct ones, and at least one carried
  value is shown to differ from what re-deriving from the rounded odds would produce.
- Unit test on the EV computation's consensus branch: given a quote with float fields set to
  values that deliberately differ from what re-deriving from the odds would produce, the
  function returns the stored floats verbatim.
- Property test: two distinct realistic odds pairs whose de-vigged probabilities differ by
  more than floating-point epsilon must still differ by more than epsilon after passing
  through the consensus average, i.e. the averaging and carrying step is injective and does
  not itself introduce new collisions.
- Existing snapshot suite re-verified; only the two previously-colliding rows change value,
  separating in the direction implied by their respective books' odds. No other row changes.
