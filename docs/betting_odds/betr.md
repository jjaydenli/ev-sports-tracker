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

Betr uses a Keycloak JWT in the `Authorization` header (raw token only — no `Bearer ` prefix). The scraper reads it from `BETR_BEARER_TOKEN` in `backend/.env`.

### Checking expiry (no API call)

JWTs are three dot-separated base64 segments. The middle segment is JSON with `iat` (issued at) and `exp` (expires at) as Unix timestamps. Decode it locally:

```bash
cd backend && .venv/bin/python -c "
import os, json, base64
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv('.env')
token = os.getenv('BETR_BEARER_TOKEN', '')
payload = json.loads(base64.urlsafe_b64decode(token.split('.')[1] + '=='))
for key in ('iat', 'exp'):
    print(key, datetime.fromtimestamp(payload[key], tz=timezone.utc).isoformat())
"
```

Or paste the token into [jwt.io](https://jwt.io) and read the `exp` claim.

### Manual refresh (current)

1. Open [fantasy.betr.app](https://fantasy.betr.app) while logged in.
2. DevTools → Network → any GraphQL request to `api.fantasy.betr.app`.
3. Copy the `Authorization` header value (strip the `Bearer ` prefix if present).
4. Update `BETR_BEARER_TOKEN` in `backend/.env`.

Verify with: `.venv/bin/python -m scrapers.dfs.betr.betr_api`

### Automated refresh (`betr_auth.py`)

The pipeline and scrapers call `ensure_betr_token()` before Betr requests:

1. Valid cached token in `data/processed/.betr_token_cache.json` (gitignored)
2. Valid `BETR_BEARER_TOKEN` from `.env`
3. Keycloak **refresh_token** grant when `BETR_REFRESH_TOKEN` (or cache) is set
4. Keycloak **password** grant when `BETR_USERNAME` and `BETR_PASSWORD` are set

JWT **expiry pre-flight** fails the run if the token is expired or expires within 24 hours (configurable in code). Override only for debugging: `python -m core.pipeline_runner --skip-expiry-check`.

**Env vars** (see `config/.env.example`):

| Variable | Purpose |
|----------|---------|
| `BETR_BEARER_TOKEN` | Manual JWT (DevTools copy) |
| `BETR_KEYCLOAK_TOKEN_URL` | Full OIDC token endpoint (optional if JWT `iss` is present) |
| `BETR_KEYCLOAK_CLIENT_ID` | Keycloak client id (optional; code default `betr-web` — override if capture differs) |
| `BETR_USERNAME` / `BETR_PASSWORD` | Password grant |
| `BETR_REFRESH_TOKEN` | Refresh grant |

If password/refresh grants return 401, use the capture checklist below.

### Auth probe

```bash
cd backend && python -m scrapers.dfs.betr.betr_auth
cd backend && python -m scrapers.dfs.betr.betr_auth --try-grant
```

Prints resolved token URL (env vs JWT `iss`), client id (env vs default `betr-web`), bearer expiry, cache presence, and optional grant result (HTTP status only — no tokens).

### Keycloak capture checklist (if grant returns 401)

1. Open [fantasy.betr.app](https://fantasy.betr.app) with DevTools → **Network** open.
2. Log in (or refresh the session) and filter requests for `openid-connect/token`.
3. Open the token **POST** request and copy:
   - **Request URL** → `BETR_KEYCLOAK_TOKEN_URL` (full path ending in `/protocol/openid-connect/token`)
   - **Form body** `client_id` → `BETR_KEYCLOAK_CLIENT_ID` only if it differs from `betr-web`
4. For password grant: set `BETR_USERNAME` / `BETR_PASSWORD` in `config/.env`.
5. For refresh grant: copy `refresh_token` from the token response → `BETR_REFRESH_TOKEN`.
6. Re-run `python -m scrapers.dfs.betr.betr_auth --try-grant`, then `./ev --skip-dk --skip-fd` to confirm hands-free Betr scrape.

**Daily command:** `cd backend && python -m core.pipeline_runner`

## API

| Operation | Purpose |
|-----------|---------|
| `LeagueUpcomingEvents` | NBA slate + all player projections in one request (`variables.league = "NBA"`) |
| `getEventByIdV2` | Single-event fallback (same projection shape) |
