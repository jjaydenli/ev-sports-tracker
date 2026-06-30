# DraftKings (sportsbook) — scrape and line matching

## Subcategory IDs (slate vs prop)

DK reuses ``subCategoryId`` at two scopes (see module docstring in `dk_subcategories.py`):

- **Slate** (`slate_subcategory_id` in `DK_LEAGUE_SLATES`): league page gateway — lists scheduled games.
- **Prop** (values in `DK_NBA_STAT_CATEGORIES` / `DK_MLB_STAT_CATEGORIES`): per-event stat tab — player O/U lines.

Event player props are fetched per prop `subCategoryId` in [`backend/config/dk_subcategories.py`](../../backend/config/dk_subcategories.py).

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

**Milestone** (1+/2+/3+, over-only) — `DK_NBA_MILESTONE_STAT_CATEGORIES` (each ID verified against DK `market` / `marketType.name`, not assumed sequential):

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

**MLB** (pregame O/U — full slate) — `DK_MLB_STAT_CATEGORIES`; slate `DK_LEAGUE_SLATES["mlb"]` uses `league_id` 84240 and `slate_subcategory_id` 4519:

| Canonical market | subCategoryId (MLB) |
|------------------|---------------------|
| hits | 6719 |
| total_bases | 6607 |
| h+r+rbi | 17406 |
| runs | 17407 |
| singles | 17409 |
| doubles | 17410 |
| walks | 17411 |
| earned_runs | 17412 |
| total_outs | 17413 |
| strikeouts | 15221 |
| pitching_walks | 15219 |
| hits_allowed | 9886 |
| rbi | 8025 |

Probe configured or pasted IDs: `python -m scripts.probe_dk_subcategories <event_id> --league mlb`. See [mlb.md](mlb.md).

Betr-only markets awaiting IDs are listed in `DK_NBA_PENDING_STAT_CATEGORIES` (skipped at scrape).

## O/U vs milestone tabs

- **O/U** (`line_kind: ou`): paired Over/Under with `points` — preferred for line matching.
- **Milestone** (`line_kind: milestone`): over-only `N+` labels; mapped to Betr half-point line `N - 0.5` (e.g. DK `2+` ↔ Betr `1.5`).

The scraper fetches O/U for every market in `DK_NBA_STAT_CATEGORIES` and milestone tabs when `DK_NBA_MILESTONE_STAT_CATEGORIES` has an ID. Per event, all subcategory calls run in parallel (capped by `DK_MARKETS_MAX_CONCURRENT`, default `6`); transient 403/429 responses are retried with backoff.

## Scrape performance and rate limits

DraftKings serves markets through Akamai on `sportsbook-nash.draftkings.com`. Blocks show up as **403 Access Denied** (HTML), not JSON rate-limit bodies. The scraper treats 403/429 as **transient** and retries with backoff while a global semaphore limits in-flight market GETs.

### HTTP budget (typical NBA slate, auto-discover)

| Step | Calls | Notes |
|------|------:|-------|
| League slate (event discovery) | 1 | Always first; also sets cookies for auto-discover |
| Warm-up league (explicit event IDs only) | +1 | Skipped when IDs come from league discovery |
| Event subcategory markets | 21 | 11 O/U + 10 milestone (`stl+blk` has no milestone tab) |

For **one** `NOT_STARTED` event, expect **22** HTTP round-trips on the happy path (1 league + 21 markets). Each extra event adds **21** market calls (events are scraped in parallel).

### Tuning `DK_MARKETS_MAX_CONCURRENT`

Set in `backend/config/.env` (see `backend/config/.env.example`).

| Value | Behavior |
|-------|----------|
| **4** | Safest if you still see 403 warnings; ~5–6 waves per event |
| **6** (default) | Balance from production debugging: ~4 waves per event |
| **8–10** | Faster when your IP is clean; watch logs for 403 retries |
| **12+** | Not recommended; reproduces the original burst that triggered Akamai |

Retries use delays **0.5s → 1s → 2s → 4s** (up to 5 attempts). A single subcategory that keeps failing adds up to ~7.5s of sleep before the scrape gives up on that tab.

### Wall-clock model (DK scrape only)

Assume ~100–200ms RTT per GET and no 403s:

```
market_time ≈ ceil(21 / DK_MARKETS_MAX_CONCURRENT) × RTT
total ≈ RTT_league + market_time
```

Examples at **RTT = 150ms**:

| Phase | `MAX_CONCURRENT=2` | `=6` (default) | `=12` (old burst) |
|-------|-------------------:|---------------:|------------------:|
| Market waves | 11 | 4 | 2 |
| Market time | ~1.65s | ~0.6s | ~0.3s |
| + league | +0.15s | +0.15s | +0.15s |
| **Typical total** | **~1.8s** | **~0.75s** | **~0.45s** (often 403s) |

Real `./ev` runs **Betr, DK, and FanDuel scrapers in parallel**, so DK wall-clock overlaps with other books; only the DK column above is isolated time on the DK client.

### Implementation history (how we got here)

1. **Original** — `DraftKingsEngine` concurrency **12**; each market task fetched O/U **then** milestone **sequentially**, but up to 12 markets at once → bursts of ~11 simultaneous GETs to the same host. No retries, minimal browser headers. **Fast when it worked; intermittent 403 Access Denied** (Akamai).
2. **Post-403 hardening** — Global semaphore **2**, engine concurrency **2**, always-on league warm-up, browser-like headers, retries with long backoff (1s–6s). **Reliable but ~2–3× slower** on market fetches.
3. **Current (speed + safety)** — One **`fetch_event_all_markets`** fan-out per event: all 21 subcategory GETs share a pipeline limited by **`DK_MARKETS_MAX_CONCURRENT` (6)**. O/U and milestone for the same stat run in **parallel**. League called **once** on auto-discover (no duplicate warm-up). Keepalive pool on `httpx.AsyncClient`. Retries shortened for faster recovery.

**Compared to original:** similar theoretical parallelism but **controlled** (6 in flight, not 11), plus retries and headers so fewer hard failures.

**Compared to post-403 hardening:** **~2–4× faster** market phase at default 6, with similar reliability if 403s were environmental.

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

**+EV eligibility:** `find_ev_opportunities` ranks `exact`, `dk_alt`, `dk_interpolated`, `fd_exact`, `fd_alt`, and `multi_book_consensus` O/U quotes. Milestone and extrapolated paths remain diagnostics-only.

EV rows include `line_source`, `betr_line`, `dk_matched_line`, `dk_main_line`, `corroborated`, `dk_line_kind` (`ou` | `milestone`).

Milestone matches use over implied probability only; under fair prob is estimated as `1 - fair_over` (not a true DK under price). The pipeline logs `one-sided` on top rows when `plus_ev_milestone_caveat` is set.

## Flat Betr lines

Integer Betr lines (e.g. 4.0 rebounds) can push and void the DFS leg. Default pipeline **skips** them. Use `python -m core.pipeline_runner --include-flat-lines` to apply the v1 push-adjusted breakeven from [`backend/core/flat_line.py`](../../backend/core/flat_line.py).
