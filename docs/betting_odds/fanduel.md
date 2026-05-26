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

| Tab (NBA) | Use |
|-----------|-----|
| `player-points` | Points O/U and related |
| `player-rebounds` | Rebounds |
| `player-assists` | Assists |
| `same-game-parlay-` | Large SGP board (many prop market types) |

**Builder:** [`build_event_page_url`](../../backend/config/fd_competitions.py)

**Event-level fields** (event-page only): `inPlay`, `primaryMarketId`, `openDate`.

**Sample market types** (from capture): `PLAYER_*_POINTS`, `2+_MADE_THREES`, `TOTAL_POINTS_(OVER/UNDER)`, `MONEY_LINE`.

Step 1 (fixture): live `GET /api/event-page` → redacted fixture `fd_event_35639109_player_points.json`.

Step 2 (flatten): `flatten_event_page_response` maps main + alt O/U ladders into master-board rows.

Step 3 (EV): `fd_normalized.json` → `resolve_multi_book_sharp_quote` — when **both** DK and FD have exact O/U at the Betr line, de-vig each book and average fair probs (equal weight; see `SHARP_BOOK_WEIGHTS`). FD is exact-only (no interpolation). If FD is exact and DK only interpolated, FD wins. `pipeline_runner` scrapes FD alongside DK; use `--skip-fd` to opt out.

```bash
cd backend && python -m core.pipeline_runner
cd backend && python -m core.pipeline_runner --skip-scrape   # reuse boards
cd backend && python -m core.pipeline_runner --skip-fd       # DK-only sharp
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
- [`backend/tests/fixtures/fd_event_35639109_player_points.json`](../../backend/tests/fixtures/fd_event_35639109_player_points.json) — redacted event-page (`player-points` tab, 5 sample markets)

## Open questions (increment 2)

| Question | Notes |
|----------|--------|
| Tab → canonical market map | `config/fd_markets.py` — `player-points` → `points`, etc. |
| Alternate lines | Alt ladder `PLAYER_*_ALT_TOTAL_*` — 1pt increments; `is_main_line` from main market |
| `inPlay` filter | Skipped in `flatten_event_page_response` when event is live |
| Milestone vs O/U | **Alt O/U only** for sharp quotes; `TO_SCORE_*` skipped (unlike DK milestones) |

## EV pipeline

Multi-book with DraftKings: `compare_betr_vs_draftkings(..., fanduel_props=)`. Output rows include `sharp_books`, `fd_over_odds`, `fd_under_odds`, `line_source` (`multi_book_consensus`, `fd_exact`, `fd_alt`, …). Adding a third sharp book requires revisiting equal-weight consensus in `line_adjustment.py`.
