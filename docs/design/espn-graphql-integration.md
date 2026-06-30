# ESPN BET (TheScore Bet) integration — GraphQL rebuild

> TheScore Bet is referred to as `espn` in all code identifiers, config, filenames, and platform
> docs. This design supersedes an earlier REST scaffold: a live API capture disproved the
> DraftKings-shaped REST assumption. The real ESPN BET API is **GraphQL persisted queries**
> (GET-based). The fetch + parse layer is a full rewrite; nothing from the `winRunnerOdds` scaffold
> is reused.

## Resolved: live MLB run — `espn:MLB=ok(938)`, 1571 O/U lines on board

The initial capture saved only GraphQL **responses**, not the browser's **request variables**, so
several ops shipped with under-specified variable sets and the live run failed op-by-op. Each
missing required variable was discovered live via `VALIDATION_INVALID_TYPE_VARIABLE` server errors.
Fixes:

- **`Startup` mint** (`scrapers/sportsbooks/espn_auth.py`): `latLongParams` was `null` — server
  requires `Float!`. Set to `{accuracy:0.0, latitude:0.0, longitude:0.0}` (null-island coordinates
  pin to the `us-default` host; real coordinates trigger a geo-region 302).
- **`CompetitionPageSectionLinesTabNode`** (`espn_api.py::fetch_games`): added required
  `includeRichEvent: true`, `oddsFormat: "AMERICAN"`, `selectedFilterId: ""` (empty = all games).
- **`EventDrawerContent`** (`espn_api.py::fetch_drawer_content`): input is
  `eventDrawerInput: {sectionSlug, eventId:"Event:<uuid>", groupId}` (no top-level `id` field)
  plus a required `oddsFormat: "AMERICAN"`. `eventId` is parsed from the drawer id.

Verified: `./ev --books espn --leagues mlb` → 938 grouped props / 1571 normalized O/U lines on the
board; `pytest -q` green.

**Game matching fix:** ESPN normalized rows initially had no `game` field, so their match-context
key (`player|market|league|[game]|event_hour`) diverged from Betr's — producing `matched=0`. Fixed
by populating `game` (`AWAY@HOME` canonical abbreviations) from `home/awayParticipant.abbreviation`
through `extract_games` → engine `_event_game_map` → `espn_parser`. Result: `matched` 0 → 89
(`--books espn`), 364 (60.2%) all-books. ESPN's team abbreviation deviation (`CWS`→`CHW`) handled
by `_ESPN_TEAM_ABBR_ALIASES` in `config/espn_competitions.py`.

---

## Goal

Add ESPN BET (TheScore Bet) as a third sharp O/U sportsbook — GraphQL scrape → parse → normalize
→ board-visible → N-book consensus — gated on a reproducible live GraphQL capture.

## Confirmed API shape

- **Transport:** GraphQL **persisted queries**, **GET**. Client sends only `sha256Hash` +
  `operationName` + `variables`; the query body is server-side and rotates per app version
  (currently `26.12.0`).
- **Host:** `https://sportsbook.us-default.thescore.bet`
- **Path:** `/graphql/persisted_queries/<sha256Hash>?operationName=<Op>&variables=<json>&extensions=<persistedQuery json>`
- **Hierarchy:**
  - `CompetitionPage` (`variables.canonicalUrl = /sport/baseball/.../competition/mlb`) → returns
    **sections** (Lines / Home Runs / Futures / …), each `{archetype, id:"Section:<uuid>", slug}`.
  - Default **Lines** section (`COMPETITION_LINES`) → `CompetitionPageSectionLinesTabNode`
    (`variables.sectionId`) → the **games list**.
  - **Player props (pitcher/batter O/U) are per-event, two hops below the Lines section** —
    EventPage → EventSection (drawer stubs) → EventDrawerContent (O/U leaf).
- **Auth:** `x-anonymous-authorization: Bearer <JWE>` (anonymous, no login). Minted via the
  `Startup` persisted-query op (no bearer required) — returns `data.startup.anonymousToken`.
  `connectToken` + `x-install-id` are client-generated random 23-char `[a-z0-9]` IDs; the server
  accepts arbitrary values, making the flow fully programmatic with zero stored secrets.
- **Cloudflare:** plain `httpx` with the captured client headers passes without challenge.
- **Market/selection shape:**
  ```
  market:    { id, name, type:"TOTAL", status, selections:[…] }
  selection: { type:"OVER"/"UNDER",
               odds:{formattedOdds:"-125"},
               points:{decimalPoints:4.5}  ← nested object, not scalar }
  ```
  O/U drawers carry literal `groupId`s (`"Hits(O/U)"`, `"TotalBases(O/U)"`, etc.); UUID-groupId
  drawers are N+/LIST milestones (deferred).

## Design decisions

1. **Validation-first gating:** Phase 0 = a runnable, authenticated live GraphQL probe returning a
   real ESPN payload, saved as the canonical fixture. No parser, pipeline, or consensus work is
   merged until Phase 0 is reproducible.

2. **Scrape model — GraphQL persisted queries:** `CompetitionPage` → Lines section →
   `CompetitionPageSectionLinesTabNode` → games; player props are per-event below Lines.
   GET persisted queries with server-side bodies. The earlier REST assumption was wrong.

3. **Separate GraphQL client:** new ESPN client in `scrapers/sportsbooks/espn_api.py`, following
   Betr's `graphql_request`/`betr_auth` conventions but isolated — ESPN uses GET persisted queries
   vs Betr's POST. Sharing a client would introduce Betr regression risk.

4. **Persisted-query registry:** `config/espn_queries.py` holds `{operationName: sha256Hash}` +
   the persisted-query `extensions` template + app version, env-overridable via
   `ESPN_APP_VERSION`. Hashes rotate together with the version; one clean home.

5. **Anonymous JWE auth:** token is an encrypted JWE (`alg:RSA-OAEP`) with no readable `exp`, so
   validity cannot be introspected like a standard JWT. Strategy: cache `(install_id,
   anonymousToken)` in `data/processed/.espn_token_cache.json` (gitignored), reuse across runs,
   re-mint reactively on 401/403 with a **stable** `install_id` (returning-device identity is
   gentler on bot-detection than a fresh random identity each run). `ensure_espn_token()` mirrors
   the `ensure_betr_token()` lifecycle; the trigger is 401, not an expiry field.

6. **Cloudflare:** plain `httpx` with captured client headers is sufficient. Cookie-priming or
   browser impersonation only if a CF block actually occurs.

7. **Leagues:** MLB first, then WNBA (NBA deferred — out of season). WNBA requires its own capture.

8. **Markets:** O/U player props only. Milestones / N+ deferred.

9. **N-book consensus (Phase 3, separate PR):** `_consensus_sharp_quote` generalization ships
   isolated from ESPN board onboarding to avoid entangling DK/FD pricing regression risk with
   new-book code.

10. **No defaulted league:** `league` is a required argument on every ESPN `fetch_*`/`flatten_*`/
    parse/config function. There is no sensible universal default; every caller already knows its
    league.

## Non-goals

- Milestones / N+ / alt-K markets
- NBA (out of season) and WNBA wiring beyond a placeholder until its own capture
- Refactoring DK/FD/Betr `league` defaults or their clients
- Sharing one GraphQL client across Betr and ESPN

## Files / modules

**Rewritten (GraphQL shape):**
- `scrapers/sportsbooks/espn_api.py` — GraphQL persisted-query client + `fetch_*`/`flatten_*`
  (CompetitionPage → Lines section → games → per-event player props via 2-hop drawer chain)
- `scrapers/sportsbooks/espn_auth.py` — `ensure_espn_token()`: `Startup` mint, JWE cache, 401
  reactive re-mint with stable `install_id`
- `parsers/espn_parser.py` — `parse_espn_props(raw)` → `NormalizedProp` rows
  (`formattedOdds` → American int, `points.decimalPoints` → line, `type` → over/under)
- `config/espn_markets.py` — drawer `groupId`/`labelText` → canonical market dispatch (O/U only)
- `config/espn_competitions.py` — `canonicalUrl` builders + section/drawer traversal helpers;
  `_ESPN_TEAM_ABBR_ALIASES` for abbreviation normalization
- `config/api_headers.py` (ESPN block) — host, client headers, `build_espn_headers()`

**New:**
- `config/espn_queries.py` — `{operationName: sha256Hash}` + `extensions` template + app version

**Unchanged downstream (book-agnostic):**
- `core/pipeline_scrape.py`, `core/ev_pipeline.py`, `parsers/normalize.py`,
  `config/pipeline_sources.py` — Phase 2 wiring only
- `core/line_adjustment.py`, `core/engine.py` — Phase 3 consensus only

## Behavior / flags

- `./ev --books espn --leagues mlb` → ESPN-only scrape; ESPN MLB O/U rows on the board (Phase 2)
- `./ev --leagues mlb` → DK + FD + ESPN consensus (Phase 3)
- Secrets via `os.getenv()` only; `ESPN_*` keys in `config/.env.example`

## Platform onboarding contract

What is reusable across books is the **contract at the edges**, never the transform in the middle.
Every book has a different payload shape, so endpoint discovery, JSON traversal, and canonical
mapping are always bespoke, written against that book's validated capture.

- **Input boundary (reusable):** `BaseScraper` lifecycle (`authenticate()` → `scrape()` →
  `save()`/`run()`) and the `fetch_*`/`flatten_*` module layout.
- **Output boundary (reusable):** every book emits the same `NormalizedProp` field set with
  canonical market names from `config/market_maps.py`, so the pipeline is book-agnostic
  downstream.

ESPN being GraphQL (like Betr) vs DK/FD REST is the exact reason copying transport internals
fails — the persisted-query GET structure is entirely different from Betr's POST even though both
use GraphQL.

## Phases

**Phase 0 — Live GraphQL validation (complete, validated 2026-06-22)**
Full chain + auth verified end-to-end (real MLB O/U rows returned; plain `httpx` passes
Cloudflare; mint is self-bootstrapping). Captures in `backend/data/processed/espn_capture/`
(gitignored). Phases 1–3 work offline from these captures.

**Phase 1 — Parser + normalize**
Implement `espn_api.py` GraphQL `fetch_*`/`flatten_*` against the captured fixtures. Market
dispatch in `config/espn_markets.py`; canonical names from `config/market_maps.py`. Tests rebound
to GraphQL fixtures.

**Phase 2 — Pipeline wiring**
Register `espn` in `BOOK_SOURCES` / `BOOK_TO_PLATFORM` / `PLATFORM_CONFIG`. Add
`scrape_espn_league(league)` to `core/pipeline_scrape.py`. Exit: `--books espn` shows ESPN rows
on the board.

**Phase 3 — N-book consensus (separate PR)**
Generalize `_consensus_sharp_quote` to `quotes: list[tuple[str, ResolvedSharpQuote]]` weighted
via `load_sharp_book_weights()`; DK+FD output stays identical (regression-locked). Add
`SHARP_BOOK_WEIGHTS_ESPN` to `config/settings.py`.

## Test plan

- `cd backend && pytest -q` (offline, GraphQL fixtures only)
- Fixtures: `espn_league_mlb_events.json`, `espn_event_*_pitcher_props.json`,
  `espn_event_*_batter_props.json` (GraphQL shape, captured Phase 0)
- Test suite mirrors the FD suite: `test_espn_api`, `test_espn_engine`, `test_espn_markets`,
  `test_normalize_espn`, `test_pipeline_sources`, `test_pipeline_runner`
- Phase 3: extend `test_line_adjustment_multi_book` (DK+FD regression + 3-book weighting +
  `SHARP_BOOK_WEIGHTS_ESPN`)
- Manual Phase 2: `./ev --books espn --leagues mlb` shows ESPN MLB O/U rows on the board
- Manual Phase 3: `./ev --leagues mlb` — DK+FD+ESPN consensus resolves; DK/FD regression intact
