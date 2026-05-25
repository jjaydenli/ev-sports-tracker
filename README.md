# EV Sports Tracker

Multi-platform Expected Value (+EV) sports betting engine. Compares fixed-payout player props on DFS apps (Dabble) against dynamically priced sportsbook lines (DraftKings) to find profitable discrepancies.

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
│   │   └── dabble_engine.py    # Relational JSON parsing
│   └── sportsbooks/
│       └── dk_engine.py        # Playwright accordion targeting
├── core/
│   ├── models.py               # NormalizedProp schemas (platform agnostic)
│   └── engine.py               # EV execution calculations
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

See [project_context.md](project_context.md) for architecture, coding standards, and roadmap. DFS breakeven odds live in [docs/BETTING_ODDS.md](docs/BETTING_ODDS.md). Dabble API capture instructions: [docs/proxyman_dabble_setup.md](docs/proxyman_dabble_setup.md).

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

   Fill in your Dabble credentials in `config/.env`. Never commit this file or bearer tokens.

4. Run tests:

   ```bash
   pytest
   ```

## Security

All API keys, passwords, and JWTs must stay in `.env` and be loaded via `os.getenv()`. Do not hardcode credentials or tokens in source files.
