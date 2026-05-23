# Master Project Context: Multi-Platform EV Betting Engine

## 1. Project Overview
This project is a high-throughput Expected Value (+EV) sports betting bot. Its primary goal is to find profitable mathematical discrepancies by comparing fixed-payout player props on Daily Fantasy Sports (DFS) apps (specifically Dabble) against dynamically priced, sharp sportsbook lines (specifically DraftKings).

The system identifies arbitrage and +EV opportunities by standardizing disparate naming conventions across books, mathematically calculating no-vig fair value on the fly, and outputting the data in a standardized JSON format.

## 2. Tech Stack & Libraries
* **Language:** Python (strictly asynchronous using `asyncio`)
* **Data Ingestion (DFS/APIs):** `httpx` for lightning-fast, asynchronous HTTP requests.
* **Data Ingestion (Sportsbooks/Web):** `playwright` with `playwright-stealth` to render JavaScript-heavy DOMs and bypass bot detection.
* **Data Processing:** `json` for relational parsing, `re` for regex string manipulation.
* **Logging:** `loguru` for color-coded, structured terminal logging.
* **Testing:** `pytest`, `pytest-asyncio`, `pytest-mock` for strict offline testing.
* *(Future Integrations): FastAPI, Redis, PostgreSQL, React.*

## 3. Platform-Specific Extraction Logic

### Dabble (DFS App)
* **Access:** App-only platform with no web interface. Traffic is reverse-engineered and intercepted via Proxyman to find hidden API endpoints, JWT Bearer tokens, and precise `User-Agent` headers.
* **Security Protocol:** All API keys and JWTs must be strictly handled via `.env` variables (`os.getenv()`). This is known as the "Scrubbed Protocol".
* **Data Structure:** Dabble's JSON payload acts like a relational SQL database. Instead of nested data, it returns flat arrays (`markets`, `prices`, `playerProps`) that must be joined together using keys like `id`, `marketId`, and `selectionId`.
* **Odds & Multipliers:** * Backend uses decimal odds (e.g., 2.55, 1.68).
    * Standard props imply a baseline of -122 odds.
    * **Lightnings & Shields:** Modifiers with varying payout multipliers (e.g., 0.7x, 1.2x). They can be restricted to one-sided bets or have explicit Over/Under offerings.

### DraftKings (Sharp Sportsbook)
* **State Management:** The frontend state is entirely driven by URL parameters (e.g., `?category=all-odds&subcategory=points`).
* **Scraping Strategy:** Instead of global regex, Playwright targets specific `.sportsbook-event-accordion` DOM elements. This "traps" the data extraction within specific market headers to prevent mislabeling combo markets (like "Pts + Reb + Ast") as standard props.
* **Orchestration:** The scraper dynamically fetches the main NBA league page, extracts all game URLs (`/event/`), deduplicates them using a Python `set()`, and loops through market subcategories concurrently.

## 4. Quantitative Modeling & Math
* **Market Mapping:** Differing market names (e.g., `threes-made` vs `3pt-made`) are run through a canonical standardizer dict (`PLATFORM_MARKET_MAPPINGS` -> `MARKETS`) to ensure accurate 1:1 comparisons.
* **De-Vigging:** DraftKings odds are converted to implied probabilities. The system strictly uses the **multiplicative method** to remove the vigorish (vig) and find the true "fair value" probability.
* **EV Calculation:** The true probability is compared against the DFS app's implied probability (e.g., the -122 baseline for standard Dabble props) to isolate +EV.

## 5. Architecture & File Structure
The project strictly follows a decoupled, multi-platform modular architecture to prevent tight coupling:

```text
ev_sports_tracker/
├── config/
│   ├── api_headers.py          # Platform-specific user-agents/headers
│   ├── market_maps.py          # Canonical market translations
│   └── .env                    # Hidden local secrets
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
│   ├── models.py               # NormalizedProp schemas (Platform agnostic)
│   └── engine.py               # EV execution calculations
└── tests/
    ├── conftest.py             # Shared fixtures and mock HTTP responses
    ├── integration/
    └── unit/

Coding Standards (Mixed Style)
Professional Externals: Use PEP 257 docstrings in Sentence Case for all function headers. Focus on intent and expected outcomes.

Developer Internals: Use Lowercase Shorthand for inline comments (e.g., # isolate network logic). Only comment the "why" behind quirks.

The Testing Mandate: Follow the AAA (Arrange, Act, Assert) pattern with logical whitespace separating blocks instead of labels.

Roadmap: Next Immediate Steps
Phase 1: Dabble Bulletproofing (Completion)
Refactor Utilities: Move decimal_to_american logic to app/utils/odds.py and update imports.

Granular Promos: Update parse_game_props to store the raw multiplier (e.g., 1.1x, 0.7x) in the grouped prop object. Distinguish between different boost levels instead of a generic "lightning" tag.

Authentication Testing: Create integration tests for get_fresh_token (mocking the login response) and get_all_active_game_ids (mocking the schedule response).

Phase 2: DraftKings Refactor
Slate Orchestration: Transition dk_engine.py from single-page scraping to dynamic slate navigation.

Accordion Logic: Implement the Playwright strategy that targets .sportsbook-event-accordion elements to safely isolate "combo" markets.

Market Mapping: Align DK extracted titles (e.g., "Pts + Reb") with the MARKET_MAPPING established in config.py.