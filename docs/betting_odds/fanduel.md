# FanDuel (sportsbook) — API discovery and event IDs

FanDuel does not publish a supported odds API. This repo uses the same JSON endpoints as the sportsbook web app (captured 2026-05-25 via `sbapi.nj.sportsbook.fanduel.com`).

## API hosts

| Host | Role |
|------|------|
| `https://sbapi.{state}.sportsbook.fanduel.com` | Primary JSON API (state-specific) |
| `https://sportsbook.fanduel.com` | Human UI; `Referer` for requests |

Default automation host: **NJ** (`FD_SPORTSBOOK_API_HOST`). Other states (`pa`, `il`, `co`, `in`, …) use the same path layout; pick the host that matches where you can access the book.

Public query param `_ak` (web client key): `FD_API_KEY` in env, default `FhMFpcPWXMeyZxOx`.

## Headers

Configured in [`backend/config/api_headers.py`](../../backend/config/api_headers.py) as `FD_BASE_HEADERS`:

- `User-Agent` — desktop Chrome
- `Accept: application/json`
- `Referer: https://sportsbook.fanduel.com/`

No bearer token observed for read-only league/event JSON (unlike Betr). Geo/state gating is enforced by **which sbapi host** you call.

## Event discovery (increment 1)

### League slate — `content-managed-page`

**URL pattern:**

```
GET {FD_SPORTSBOOK_API_HOST}/api/content-managed-page
  ?currencyCode=USD
  &exchangeLocale=en_US
  &includePrices=true
  &language=en
  &regionCode=NAMERICA
  &_ak={FD_API_KEY}
  &page=CUSTOM
  &customPageId=nba
```

**Builder:** [`build_content_managed_page_url`](../../backend/config/fd_competitions.py)

**Response shape:**

- `layout` — page tabs (not used for ID discovery)
- `attachments.events` — dict keyed by `eventId` string
- `attachments.competitions` — e.g. `10547864` = NBA, `12739957` = NBA Futures
- `attachments.markets` — markets for events on the page (large; trimmed in fixtures)

**Event ID field:** `attachments.events[<id>].eventId` (dict key usually matches).

**Scrapable games filter** (no `NOT_STARTED` on slate):

1. `competitionId == 10547864` (NBA main competition, not futures)
2. `name` matches `Team @ Team` (`\s@\s`) to drop Draft / Awards / Futures titles on the same page

Parser: [`extract_event_ids`](../../backend/config/fd_competitions.py) · live fetch: [`fetch_league_event_ids`](../../backend/scrapers/sportsbooks/fd_api.py)

**Probe:**

```bash
cd backend && python -m scripts.probe_fd_events --league nba
```

### Human URL override

Event pages end with the numeric id, e.g.:

`https://sportsbook.fanduel.com/basketball/nba/san-antonio-spurs-@-oklahoma-city-thunder-35639109`

Regex: trailing `-{eventId}` — [`parse_event_id_from_url`](../../backend/config/fd_competitions.py).

## Per-event markets (increment 2) + EV (increment 3)

**Endpoint:** `GET /api/event-page` with `eventId` and `tab`.

**Builder:** [`build_event_page_url`](../../backend/config/fd_competitions.py)

**Event-level fields** (event-page only): `inPlay`, `primaryMarketId`, `openDate`. In-play events are skipped during flatten (`event_page_in_play`).

### Market catalog

Source of truth: [`backend/config/fd_markets.py`](../../backend/config/fd_markets.py). Canonical keys match `market_maps.py` / Betr / DK.

#### Default scrape (`FD_DEFAULT_SCRAPE_MARKETS`)

`pipeline_runner` and `fd_engine` scrape these unless you pass a custom `markets=` list:

| Canonical | Tab / fetch | `marketType` pattern (main / alt) |
|-----------|-------------|-----------------------------------|
| `points` | `player-points` | `PLAYER_*_TOTAL_POINTS` / `PLAYER_*_ALT_TOTAL_POINTS` |
| `rebounds` | `player-rebounds` | `PLAYER_*_TOTAL_REBOUNDS` / `PLAYER_*_ALT_TOTAL_REBOUNDS` |
| `assists` | `player-assists` | `PLAYER_*_TOTAL_ASSISTS` / `PLAYER_*_ALT_TOTAL_ASSISTS` |
| `threes` | `same-game-parlay-` (filtered) | `PLAYER_*_TOTAL_MADE_3_POINT_FIELD_GOALS` / alt |
| `pts+reb` | SGP | `PLAYER_*_TOTAL_PTS_+_REB` (also `POINTS_+_REBOUNDS`) |
| `pts+ast` | SGP | `PLAYER_*_TOTAL_PTS_+_AST` (`POINTS_+_ASSISTS`) |
| `pra` | SGP | `PLAYER_*_TOTAL_PTS_+_REB_+_AST` (`POINTS_+_REB_+_AST`) |
| `reb+ast` | SGP | `PLAYER_*_TOTAL_REB_+_AST` (`REBOUNDS_+_ASSISTS`) |

Core stats use one dedicated tab each (`FD_TAB_CANONICAL_MARKETS`). Extended combo stats and threes share a **single** SGP tab request per event; `fd_engine.scrape_targets_for_markets` filters `marketType` to the requested canonical set.

Parser: `parse_player_ou_market_type` — regex `^PLAYER_[A-Z]_(ALT_)?TOTAL_(?P<stat>.+)$` with suffix → canonical via `_STAT_SUFFIX_TO_CANONICAL` (longest match first).

#### On the board but not scraped (sharp / EV)

Present on event-page JSON (especially SGP and stat tabs) but **ignored** by `flatten_event_page_response` today:

| Family | Example `marketType` | Notes |
|--------|-------------------|--------|
| Milestone (score) | `TO_SCORE_10+_POINTS`, `TO_SCORE_25+_POINTS` | Yes/no ladders; unlike DK milestone sharp policy |
| Milestone (record) | `TO_RECORD_6+_REBOUNDS`, `TO_RECORD_10+_ASSISTS` | Same |
| Made-threes milestone | `2+_MADE_THREES`, `N+_MADE_THREES` | Not O/U ladders |
| Double / triple | `TO_RECORD_A_DOUBLE-DOUBLE`, triple-double variants | |
| Quarter / half | `1ST_QUARTER_-_TO_SCORE_*`, period splits | |
| Game lines | `MONEY_LINE`, `TOTAL_POINTS_(OVER/UNDER)`, spreads | |
| Steals / blocks O/U | — | **Not observed** on FD NBA event pages (2026-05-26 probe) |

Future work: branch `feat/fd-milestone-props` — ingest `TO_SCORE_*` / `TO_RECORD_*` / double-double boards with DK-like milestone EV policy.

#### Alternate lines

- Main: `PLAYER_{A–Z}_TOTAL_{STAT}` — one primary line per player (`is_main_line=True` in flatten).
- Alt: `PLAYER_{A–Z}_ALT_TOTAL_{STAT}` — 1-point ladder steps; grouped under one master-board prop per player + canonical market (`group_fd_line_rows`).

### Pipeline flow

1. **Fixture / live fetch:** `GET /api/event-page` → e.g. `fd_event_35639109_player_points.json` (and `*_rebounds`, `*_assists` for core tabs).
2. **Flatten:** `flatten_event_page_response` — main + alt O/U only → grouped `fd_master_board.json`.
3. **EV:** `fd_normalized.json` → `resolve_multi_book_sharp_quote` — when **both** DK and FD have exact O/U at the Betr line, de-vig each book and average fair probs (env-tunable weights via `load_sharp_book_weights()` / `SHARP_BOOK_WEIGHTS_DK` / `SHARP_BOOK_WEIGHTS_FD`, default 1.0 each). FD is exact-only (no interpolation). If FD is exact and DK only interpolated, FD wins. `pipeline_runner` scrapes Betr + DK + FD in parallel; use `--skip-fd` / `--skip-dk` to reuse existing normalized boards.

```bash
cd backend && python -m core.pipeline_runner
cd backend && python -m core.pipeline_runner --skip-scrape   # reuse boards
cd backend && python -m core.pipeline_runner --skip-fd       # omit FD scrape; reuse fd_normalized.json
```

## NBA constants (verified 2026-05-25)

| Key | Value |
|-----|-------|
| `customPageId` | `nba` |
| `competitionId` (NBA) | `10547864` |
| `eventTypeId` (basketball) | `7522` |
| Example event id | `35639109` (Spurs @ Thunder) |

## Incremental verification (build one layer, test before next)

| Step | What | Command |
|------|------|---------|
| 1 | URL builders (offline) | `cd backend && pytest tests/unit/test_fd_event_discovery.py::test_build_content_managed_page_url_includes_nba_page -q` |
| 2 | Fixture parse / `extract_event_ids` | `pytest tests/unit/test_fd_event_discovery.py::test_extract_event_ids_returns_matchups_only -q` |
| 3 | Mocked `fetch_league_event_ids` | `pytest tests/unit/test_fd_event_discovery.py::test_fetch_league_event_ids -q` |
| 4 | Live slate (network) | `python -m scripts.probe_fd_events --league nba` |
| 5 | URL parse smoke | `python -m scripts.probe_fd_events --game-url 'https://sportsbook.fanduel.com/basketball/nba/...-35639109' --event-id 35639109` |
| 6 | Full suite | `cd backend && pytest -q` |

Do not add `fd_engine` / flatten until step 4 matches the browser slate.

## Fixtures

- [`backend/tests/fixtures/fd_league_nba_events.json`](../../backend/tests/fixtures/fd_league_nba_events.json) — redacted league page (6 events, 5 sample markets)
- [`backend/tests/fixtures/fd_event_35639109_player_points.json`](../../backend/tests/fixtures/fd_event_35639109_player_points.json) — redacted event-page (`player-points` tab)
- [`backend/tests/fixtures/fd_event_35639109_player_rebounds.json`](../../backend/tests/fixtures/fd_event_35639109_player_rebounds.json) — `player-rebounds` tab
- [`backend/tests/fixtures/fd_event_35639109_player_assists.json`](../../backend/tests/fixtures/fd_event_35639109_player_assists.json) — `player-assists` tab

SGP / extended O/U: use live `probe_fd_events --tab same-game-parlay-` or add a redacted fixture when stabilizing extended-market tests.

## EV pipeline

Multi-book with DraftKings: `compare_betr_vs_draftkings(..., fanduel_props=)`. Output rows include `sharp_books`, `fd_over_odds`, `fd_under_odds`, `line_source` (`multi_book_consensus`, `fd_exact`, `fd_alt`, …). Adding a third sharp book requires revisiting equal-weight consensus in `line_adjustment.py`.
