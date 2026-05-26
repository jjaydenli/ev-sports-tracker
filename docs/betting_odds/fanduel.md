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

## Per-event markets (increment 2 — not implemented)

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

Increment 2 will map tabs → canonical markets and flatten `attachments.markets` / `runners` into `fd_master_board.json` (mirror DraftKings rows).

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

## Open questions (increment 2)

| Question | Notes |
|----------|--------|
| Tab → canonical market map | Confirm `player-points` / `player-rebounds` / … vs `same-game-parlay-` for full ladders |
| Alternate lines | DK uses `MainPointLine`; FD runner/handicap shape TBD |
| `inPlay` filter | Slate lacks status; may filter via event-page before scrape |
| Multi-state host | Document which `sbapi.*` host matches your account |

## EV pipeline

Not wired yet. Roadmap: multi-book exact alts with DraftKings in `resolve_sharp_quote` ([`project_context.md`](../../project_context.md) §6).
