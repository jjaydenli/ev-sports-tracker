# DraftKings (sportsbook) — scrape and line matching

## Subcategory IDs

Event player props are fetched per `subCategoryId` in [`backend/config/dk_subcategories.py`](../../backend/config/dk_subcategories.py).

| Canonical market | subCategoryId (NBA, verified) |
|------------------|----------------------------|
| points | 12488 |
| rebounds | 12492 |
| assists | 12495 |
| threes | 12497 |
| steals | 2713508 |
| blocks | 2713780 |
| stl+blk | 2713781 |
| pra | 5001 |
| pts+reb | 9976 |
| pts+ast | 9973 |
| reb+ast | 9974 |

**Milestone** (1+/2+/3+, over-only) — `DK_MILESTONE_STAT_CATEGORIES` (each ID verified against DK `market` / `marketType.name`, not assumed sequential):

| Canonical market | subCategoryId (NBA) |
|------------------|----------------------------|
| points | 2716477 |
| rebounds | 2716479 |
| assists | 2716478 |
| threes | 2716480 |
| pts+reb | 2716482 |
| pts+ast | 2716481 |
| reb+ast | 2719560 |
| pra | 2716483 |
| blocks | 2716484 |
| steals | 2716485 |

`stl+blk` has O/U on DK (`2713781`) but no 1+/2+/3+ milestone tab. `reb+ast` milestone id is outside the default probe scan range (`2716474–2716491`).

Betr-only markets awaiting IDs are listed in `DK_PENDING_STAT_CATEGORIES` (skipped at scrape).

## O/U vs milestone tabs

- **O/U** (`line_kind: ou`): paired Over/Under with `points` — preferred for line matching.
- **Milestone** (`line_kind: milestone`): over-only `N+` labels; mapped to Betr half-point line `N - 0.5` (e.g. DK `2+` ↔ Betr `1.5`).

The scraper fetches O/U for every market in `DK_STAT_CATEGORIES` and milestone tabs when `DK_MILESTONE_STAT_CATEGORIES` has an ID.

## Alternate lines

[`backend/scrapers/sportsbooks/dk_api.py`](../../backend/scrapers/sportsbooks/dk_api.py) ingests all Over/Under selections with a `points` value (main `MainPointLine` tag plus alternates). Each row includes `is_main_line`.

## Line alignment (Betr vs DK)

[`backend/core/line_adjustment.py`](../../backend/core/line_adjustment.py) resolves DK prices onto the Betr line.

**O/U (preferred):**

1. **exact** / **dk_alt** — DK has the same line (`corroborated: true`)
2. **dk_interpolated** — bracket between two DK O/U lines (logit interpolation)
3. **dk_extrapolated** — single O/U anchor (usually main); `corroborated: false`

**Milestone fallback** (when O/U is missing or only `dk_extrapolated`):

4. **dk_milestone_exact** / **dk_milestone_interpolated** / **dk_milestone_extrapolated** — over-only N+ ladder; always `corroborated: false`

Extrapolation shifts fair probabilities in logit space by `EXTRAPOLATION_LOGIT_SHIFT_PER_POINT[market]` per 1.0 point of gap (`anchor - target`). Lower target vs anchor raises over probability. Extrapolation is for diagnostics only until FanDuel (or other books) supply exact alts.

**+EV eligibility:** `find_ev_opportunities` ranks only `exact`, `dk_alt`, and `dk_interpolated` true O/U quotes (`is_ev_eligible_quote`). `dk_extrapolated`, milestone methods, and other non-exact paths yield `no_exact_sharp_line` in match stats and are omitted from `ev_opportunities.json`. After FanDuel (or other books) alt lines are scraped, extrapolation output can be calibrated against those exact alts; it remains out of ranked +EV until then.

EV rows include `line_source`, `betr_line`, `dk_matched_line`, `dk_main_line`, `corroborated`, `dk_line_kind` (`ou` | `milestone`).

Milestone matches use over implied probability only; under fair prob is estimated as `1 - fair_over` (not a true DK under price). The pipeline logs `one-sided` on top rows when `plus_ev_milestone_caveat` is set.

## Flat Betr lines

Integer Betr lines (e.g. 4.0 rebounds) can push and void the DFS leg. Default pipeline **skips** them. Use `python -m core.pipeline_runner --include-flat-lines` to apply the v1 push-adjusted breakeven from [`backend/core/flat_line.py`](../../backend/core/flat_line.py).
