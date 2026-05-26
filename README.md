# EV Sports Tracker

Multi-platform Expected Value (+EV) sports betting engine. Compares fixed-payout player props on DFS apps (primarily **Betr**) against dynamically priced sportsbook lines (**DraftKings**) to find profitable discrepancies.

## Repository layout

```
backend/
├── config/
│   ├── api_headers.py          # Platform-specific user-agents/headers
│   ├── market_maps.py          # Canonical market translations
│   ├── settings.py             # Credential loading from .env
│   └── .env.example            # Template for local secrets
├── utils/
│   ├── math_utils.py           # Multiplicative de-vigging, conversion formulas
│   └── formatting.py           # Standardizers (names, leagues, teams)
├── scrapers/
│   ├── base_scraper.py         # Abstract base class enforcing standard pipeline
│   ├── dfs/
│   │   ├── betr/               # Betr GraphQL (httpx)
│   │   └── dabble_engine.py    # Legacy
│   └── sportsbooks/
│       ├── dk_engine.py        # DraftKings markets API (httpx)
│       └── dk_api.py
├── parsers/
│   ├── betr_parser.py, dk_parser.py, normalize.py
├── core/
│   ├── models.py               # NormalizedProp schemas (platform agnostic)
│   ├── engine.py               # EV calculations
│   └── ev_pipeline.py          # Unified board → EV output
├── tests/
│   ├── conftest.py             # Shared fixtures and mock HTTP responses
│   ├── integration/
│   └── unit/
├── data/
│   ├── raw/                    # Local scrape output (gitignored)
│   └── processed/              # Parsed/normalized output (gitignored)
├── requirements.txt
└── pytest.ini
```


## Setup

1. Create and activate a virtual environment:

   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Configure credentials locally:

   ```bash
   cp config/.env.example config/.env
   ```

   Fill in platform tokens (e.g. `BETR_BEARER_TOKEN`) in `config/.env`. Never commit this file or bearer tokens.

4. Run tests:

   ```bash
   pytest
   ```

## Daily refresh

From the repo root (activates `backend/.venv` if present) or from `backend/` with `.venv` active:

```bash
./ev
# same as: cd backend && python -m core.pipeline_runner
```

This runs Betr scrape → DraftKings scrape → normalize → EV scan and writes:

- `data/processed/ev_opportunities.json` — top matched plays by EV (default 15)
- `data/processed/match_report.json` — matched/unmatched counts and `betr_match_rate_pct`
- `data/processed/unmatched_betr.json` — Betr lines with no DK match (or DK missing odds)
- `data/processed/unmatched_dk.json` — DK lines with no Betr twin on the same key

Use the match files to judge scrape coverage and cross-book alignment before trusting +EV rows. Useful flags:

- `--skip-scrape` — reuse existing master boards
- `--skip-betr` / `--skip-dk` / `--skip-fd` — sharp-only refresh: scrape the others, reuse that book’s normalized file for EV
- `--betr-only` / `--dk-only` — scrape one book only
- `--top-n 15` — max rows written (default 15)
- `--min-ev 0.01` — mark `plus_ev` when edge > 1%; also **filters** output to those rows (default `0` shows all edges in top-N)
- `--plus-ev-only` — filter to `ev > --min-ev` (use with `--min-ev 0` for strictly positive EV only)
- `--include-flat-lines` — include Betr integer lines (push-adjusted breakeven; off by default)

DK subcategories, alternate lines, and line alignment: [docs/betting_odds/draftkings.md](docs/betting_odds/draftkings.md).

Betr auth: set `BETR_BEARER_TOKEN`, or configure `BETR_USERNAME` / `BETR_PASSWORD` (and optionally `BETR_KEYCLOAK_TOKEN_URL`, `BETR_KEYCLOAK_CLIENT_ID`) for automatic Keycloak refresh. See [docs/betting_odds/betr.md](docs/betting_odds/betr.md).

## Security

All API keys, passwords, and JWTs must stay in `.env` and be loaded via `os.getenv()`. Do not hardcode credentials or tokens in source files.
