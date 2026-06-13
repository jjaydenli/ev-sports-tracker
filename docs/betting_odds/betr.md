# Betr Fair Odds

Reference breakeven implied probability for Betr pick'em player props. Betr does not publish per-leg American odds on individual projections; lines are offered as even-money style picks with platform-specific boosted and edge variants.

## Single-leg baseline

| Structure | Implied probability | American |
|-----------|---------------------|----------|
| Standard pick (REGULAR) | 54.55% | -120 |

Use **-120** (`54.55%` implied) as the default `dfs_breakeven_odds` when comparing de-vigged sportsbook prices to Betr standard lines in the EV engine.

## Side availability (`allowedOptions`)

Each projection includes `allowedOptions` from the `LeagueUpcomingEvents` GraphQL response. Each option has:

| Field | Meaning |
|-------|---------|
| `marketOptionId` | Betr internal option id |
| `outcome` | Bettable side: `OVER`, `UNDER`, `MORE`, or `LESS` |

The parser maps `OVER`/`MORE` → over and `UNDER`/`LESS` → under. Unlisted sides get `over_odds` / `under_odds` = `None`. The EV engine only evaluates sides that are available on Betr.

`REGULAR` props with empty `allowed_options` are skipped (never assume both sides).

## Wide fetch policy

The scraper requests app-parity analytical fields on each slate pull and stores them on `betr_master_board.json` (snake_case). Normalization only interprets `allowed_options` today; other fields are reserved for later work:

| Raw field | Future use |
|-----------|------------|
| `non_regular_percentage`, `non_regular_value`, `type` | Boost/edge breakeven |
| `player_recent_stats` | Hit-rate / L5 filters |
| `data_feed_source_ids` | Cross-book event matching |
| `current_value` | Live in-game lines |
| `competition_type`, `venue_details` | Context / display |

UI-only fields (team icons, colors, `__typename`) are omitted from the query.

## Projection types

| Betr `type` | `prop_type` | Notes |
|-------------|-------------|-------|
| `REGULAR` | `standard` | Main board line; use -120 breakeven + `allowedOptions` |
| `MINI_BOOSTED`, `BOOSTED`, `SUPER_BOOSTED` | `boosted` | Alternate line in `non_regular_value` when `value` is a teaser anchor |
| `EDGE`, `EDGE_1`, `EDGE_3` | `edge` | Promotional edge lines |

Boosted and edge legs may need separate breakeven assumptions once payout structure is confirmed; until then treat only `standard` props with the -120 baseline.

## Authentication

Betr uses a Keycloak JWT in the `Authorization` header (raw token only — no `Bearer ` prefix). Credentials live in `backend/config/.env` or `backend/.env` (loaded by `config/settings.py`).

### Recommended: refresh grant (hands-free)

For daily `./ev` runs, configure Keycloak refresh in `config/.env`:

| Variable | Required | Purpose |
|----------|----------|---------|
| `BETR_REFRESH_TOKEN` | yes | Refresh grant from DevTools token response |
| `BETR_KEYCLOAK_TOKEN_URL` | yes* | Full OIDC token endpoint (`…/protocol/openid-connect/token`) |
| `BETR_KEYCLOAK_CLIENT_ID` | often | Keycloak client id from DevTools form body (e.g. `betr-rn`; code default `betr-web` if unset) |

\* **Token URL auto-discovery:** if you omit `BETR_KEYCLOAK_TOKEN_URL`, the code derives it from the JWT `iss` claim on any of: `BETR_BEARER_TOKEN` (even expired), cached `access_token` in `data/processed/.betr_token_cache.json`, or the `token` argument. Refresh-only setups with no JWT anywhere must set `BETR_KEYCLOAK_TOKEN_URL` explicitly.

**First-time capture** (DevTools → Network → filter `openid-connect/token`):

1. Open [fantasy.betr.app](https://fantasy.betr.app) while logged in.
2. Open the token **POST** request and copy:
   - **Request URL** → `BETR_KEYCLOAK_TOKEN_URL`
   - **Form body** `client_id` → `BETR_KEYCLOAK_CLIENT_ID` when it differs from `betr-web`
   - **Response** `refresh_token` → `BETR_REFRESH_TOKEN`
3. Probe and test:

```bash
cd backend && python -m scrapers.dfs.betr.betr_auth
cd backend && python -m scrapers.dfs.betr.betr_auth --try-grant
./ev --skip-dk --skip-fd
```

Successful probe shows `token_url: https://… [env:BETR_KEYCLOAK_TOKEN_URL]` or `[jwt:iss (…)]`, `grant_configured: refresh_token`, and `--try-grant` → `ok: True`.

After a successful grant, `betr_auth.py` writes `data/processed/.betr_token_cache.json` (gitignored) with fresh `access_token` + `refresh_token`. Copy this file when moving machines so `iss` discovery works before the first refresh.

### Token resolution order (`ensure_betr_token`)

The pipeline and scrapers call `ensure_betr_token()` before Betr requests:

1. Valid cached `access_token` in `.betr_token_cache.json`
2. Valid `BETR_BEARER_TOKEN` from `.env`
3. Keycloak **refresh_token** grant when `BETR_REFRESH_TOKEN` (or cache) is set
4. Keycloak **password** grant when `BETR_USERNAME` and `BETR_PASSWORD` are set

JWT **expiry pre-flight** fails the run if the access token is expired or expires within 24 hours. Override only for debugging: `python -m core.pipeline_runner --skip-expiry-check`.

### Alternative: manual bearer JWT

1. Open [fantasy.betr.app](https://fantasy.betr.app) while logged in.
2. DevTools → Network → any GraphQL request to `api.fantasy.betr.app`.
3. Copy the `Authorization` header value (strip the `Bearer ` prefix if present).
4. Set `BETR_BEARER_TOKEN` in `config/.env`.

Verify with: `python -m scrapers.dfs.betr.betr_api`

Re-paste when expired, or pair with `BETR_REFRESH_TOKEN` so step 3 of the resolution order takes over automatically (`iss` from the expired bearer supplies the token URL).

### Alternative: password grant

Set `BETR_USERNAME`, `BETR_PASSWORD`, and the same `BETR_KEYCLOAK_*` vars as refresh. Same token URL rules apply.

### Checking JWT expiry (no API call)

JWTs are three dot-separated base64 segments. The middle segment is JSON with `iat` and `exp` as Unix timestamps:

```bash
cd backend && python -m scrapers.dfs.betr.betr_auth
```

Or paste the token into [jwt.io](https://jwt.io) and read the `exp` claim.

### Auth probe

```bash
cd backend && python -m scrapers.dfs.betr.betr_auth
cd backend && python -m scrapers.dfs.betr.betr_auth --try-grant
```

Prints resolved token URL (env vs JWT `iss` source), client id, `env_bearer` / `cache_access` expiry (when applicable), cache presence, grant type, and optional grant result (HTTP status only — no secrets).

**Common probe failures**

| Output | Fix |
|--------|-----|
| `token_url: (not resolved) [missing]` | Set `BETR_KEYCLOAK_TOKEN_URL`, or add a JWT with `iss` (`BETR_BEARER_TOKEN` or copy `.betr_token_cache.json` from another machine) |
| `grant_probe: ok: False` + HTTP 401 | Re-capture `client_id`, `token_url`, and `refresh_token` from DevTools |
| `cache_access_expires_within_24h: True` (or `env_bearer_expires_within_24h`) on pipeline | Run `--try-grant` or paste a fresh bearer |

If password/refresh grants return 401 after capture, re-check `client_id` (mobile/web clients differ, e.g. `betr-rn` vs `betr-web`).

**Daily command:** `cd backend && python -m core.pipeline_runner` (or repo-root `./ev`)

## API

| Operation | Purpose |
|-----------|---------|
| `LeagueUpcomingEvents` | NBA slate + all player projections in one request (`variables.league = "NBA"`) |
| `getEventByIdV2` | Single-event fallback (same projection shape) |
