# ESPN / TheScore Bet (ESPN BET) — API shape and EV hooks

The product is **TheScore Bet / ESPN BET**; code identifiers use **`espn`** (`espn_api.py`,
`espn_engine.py`, `espn_auth.py`, `espn_parser.py`, platform key `espn`).

## Status

**Validated live 2026-06-22** (app version `26.12.0`). The real API is **GraphQL persisted
queries (GET)** — not the FanDuel/DK REST shape the original scaffold assumed. Scrape → parse →
normalize → board-visible on `espn_master_board.json` / `espn_normalized.json` /
`unified_master_board.json`. O/U player props only (milestones/N+ deferred).

## Transport — GraphQL persisted queries (GET)

The client sends only `operationName` + `variables` + an `extensions` blob carrying the query's
`sha256Hash`; the query body is server-side and **rotates with the app version**.

```
GET {host}/graphql/persisted_queries/<sha256Hash>?operationName=<Op>&variables=<json>&extensions=<persistedQuery json>
```

| Env | Role |
|-----|------|
| `ESPN_SPORTSBOOK_API_HOST` | Base host (default `https://sportsbook.us-default.thescore.bet`) |
| `ESPN_APP_VERSION` | App build; bump **with** the hashes in `config/espn_queries.py` on rotation (default `26.12.0`) |
| `ESPN_ORIGIN` / `ESPN_REFERER` | `https://sportsbook.thescore.bet` |
| `ESPN_INSTALL_ID` | Optional pinned install id (else generated + cached) |

Hashes + `extensions` template: [`config/espn_queries.py`](../../backend/config/espn_queries.py).
Client headers + `build_espn_headers()`: [`config/api_headers.py`](../../backend/config/api_headers.py).

## Auth — anonymous JWE (no login)

Reads carry `x-anonymous-authorization: Bearer <JWE>`. The token is minted by the **`Startup`**
persisted-query op (GET, **no** bearer) → `data.startup.anonymousToken`. `connectToken` and
`x-install-id` are client-generated random 23-char `[a-z0-9]` ids the server accepts as-is, so the
flow is fully programmatic with **zero stored secrets** (a static `ESPN_ANON_TOKEN` stays rejected).

The token is an **encrypted** JWE (`alg:RSA-OAEP`) with no readable `exp`, so it cannot be
introspected like Betr's JWT. `ensure_espn_token()` ([`espn_auth.py`](../../backend/scrapers/sportsbooks/espn_auth.py))
caches `(install_id, anonymous_token)` in `data/processed/.espn_token_cache.json` (gitignored),
reuses it across runs with a **stable** install id, and re-mints reactively on a **401/403** (the
GraphQL client retries once). Cloudflare (`__cf_bm` / `_cfuvid`) is passed by plain `httpx` with the
client-parity headers; escalate only if it actually blocks (decision 6).

## Read chain (per league)

`CompetitionPage` (`canonicalUrl` → sections) → `CompetitionPageSectionLinesTabNode`
(Lines section → games, `StandardEvent:<uuid>`) → `EventPage` (`canonicalUrl` → prop sections,
slugs `pitcher-props`/`batter-props`) → `EventSection` (→ drawer stubs) → `EventDrawerContent`
(→ the O/U leaf). **Player props are two hops below the event.**

O/U drawers carry **literal** `groupId`s (`PitcherStrikeouts(O/U)`, `Hits(O/U)`, `TotalBases(O/U)`,
`RBIs(O/U)`, `HomeRuns(O/U)`); UUID-`groupId` drawers are the N+/LIST milestone boards (deferred).

### O/U leaf shape

```
data.eventDrawer.drawerChildren[].marketplaceShelfChildren[].markets[]
market:    { id, name:"<Player> Total <Stat>", type:"TOTAL", selections:[…] }
selection: { type:"OVER"/"UNDER", odds.formattedOdds:"-155", points.decimalPoints:4.5 }
```

American odds = `selection.odds.formattedOdds`; line = `selection.points.decimalPoints` (**nested**,
not a scalar); over/under = `selection.type`. Player name from `market.name` (`"<Player> Total …"`).
Traversal helpers: [`config/espn_competitions.py`](../../backend/config/espn_competitions.py);
group-id → canonical: [`config/espn_markets.py`](../../backend/config/espn_markets.py).

## Leagues

| League | Slate config | Markets |
|--------|--------------|---------|
| **MLB** (shipped) | `ESPN_LEAGUE_SLATES["mlb"]` (canonicalUrl + Lines section id) | strikeouts, hits, total_bases, rbi, home_runs (O/U) |
| **WNBA** (registered) | `ESPN_LEAGUE_SLATES["wnba"]` — canonicalUrl/section ids TBD after its own capture | TBD |
| NBA | Deferred (out of season) | — |

## Probe (live)

```bash
cd backend && python -m scripts.probe_espn_events --league mlb
```

Mints the JWE, walks the read chain, and prints flattened O/U rows.

## Pipeline

```bash
./ev --books espn --leagues mlb          # ESPN-only partial scrape
./ev --leagues mlb                       # full run incl. ESPN when in BOOK_SOURCES
```

Registry: `config/pipeline_sources.py` (`BOOK_SOURCES`, `BOOK_TO_PLATFORM`).

## EV / consensus

- Normalized rows: `espn_normalized.json` → `load_comparison_inputs` / `active_sources` on partial runs.
- **Multi-book consensus:** when two or more sharp books (DK, FD, ESPN) have exact O/U at the Betr
  line, `_consensus_sharp_quote` weights de-vigged fair probs via `SHARP_BOOK_WEIGHTS_ESPN`
  (default `1.0`, next to DK/FD in `config/settings.py`).
- ESPN resolution: exact O/U only (`espn_exact` / `espn_alt`), mirroring FanDuel — no interpolation.

## Fixtures (offline tests)

Trimmed GraphQL captures under `tests/fixtures/`:
`espn_lines_games.json`, `espn_event_page.json`, `espn_event_section_{pitcher,batter}.json`,
`espn_drawer_{pitcher_strikeouts,batter_hits}.json`.
