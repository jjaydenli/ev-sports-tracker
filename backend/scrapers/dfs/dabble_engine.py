import asyncio
import httpx
from loguru import logger

from config.api_headers import (
    DABBLE_AUTH_URL,
    DABBLE_BASE_HEADERS,
    DABBLE_FIXTURE_DETAIL_URL,
    DABBLE_SCHEDULE_URL,
)
from config.market_maps import DABBLE_MARKET_MAP
from config.settings import DABBLE_PASSWORD, DABBLE_USERNAME
from scrapers.base_scraper import BaseScraper
from utils.math_utils import decimal_to_american


async def get_fresh_token():
    """Logs into Dabble and returns a fresh Bearer token."""
    logger.info("Authenticating with Dabble...")
    payload = {"username": DABBLE_USERNAME, "password": DABBLE_PASSWORD}

    async with httpx.AsyncClient(verify=False) as client:
        try:
            response = await client.post(
                DABBLE_AUTH_URL, headers=DABBLE_BASE_HEADERS, json=payload
            )
            response.raise_for_status()
            data = response.json()

            token = data.get("idToken") or data.get("access_token") or data.get("accessToken")
            if token:
                logger.success("Successfully generated fresh Bearer token.")
                return token

            logger.error("Token not found in response.")
            return None
        except Exception as exc:
            logger.error(f"Authentication failed: {exc}")
            return None


async def get_all_active_game_ids(bearer_token):
    """Hits the schedule endpoint to extract all unique active game IDs on the board."""
    logger.info("Fetching all Game IDs from the Dabble board...")
    headers = DABBLE_BASE_HEADERS.copy()
    headers["Authorization"] = f"Bearer {bearer_token}"

    unique_game_ids = set()

    async with httpx.AsyncClient(verify=False) as client:
        try:
            response = await client.get(DABBLE_SCHEDULE_URL, headers=headers)
            response.raise_for_status()
            data = response.json()

            for prop in data.get("data", []):
                fixture_id = prop.get("fixtureId")
                if fixture_id:
                    unique_game_ids.add(fixture_id)

            logger.success(f"Found {len(unique_game_ids)} total active NBA games.")
            return list(unique_game_ids)
        except Exception as exc:
            logger.error(f"Failed to fetch game IDs: {exc}")
            return []


def parse_game_props(sport_fixture_detail):
    """
    Parses a single game's relational JSON structure.
    Links markets, prices, and playerProps together using their IDs.
    """
    markets = sport_fixture_detail.get("markets", [])
    prices = sport_fixture_detail.get("prices", [])
    player_props = sport_fixture_detail.get("playerProps", [])

    active_markets = {}
    for market in markets:
        if market.get("isDfsAllowed") and market.get("status") == "open":
            active_markets[market["id"]] = market.get("resultingType", "")

    price_map = {}
    market_price_counts = {}
    for price in prices:
        selection_id = price.get("selectionId")
        market_id = price.get("marketId")

        if selection_id:
            price_map[selection_id] = price.get("price")

        if market_id:
            market_price_counts[market_id] = market_price_counts.get(market_id, 0) + 1

    grouped_props = {}

    for prop in player_props:
        market_id = prop.get("marketId")
        if market_id not in active_markets:
            continue

        player_name = prop.get("playerName")
        raw_market = active_markets[market_id]
        line = prop.get("value")
        line_type = prop.get("lineType")
        selection_id = prop.get("selectionId")
        standard_market = DABBLE_MARKET_MAP.get(raw_market, raw_market)
        raw_price = price_map.get(selection_id)
        market_occurrences = market_price_counts.get(market_id, 0)

        if raw_price:
            american_odds = decimal_to_american(raw_price)
        else:
            american_odds = None

        if market_occurrences == 1:
            prop_type = "lightning" if raw_price and raw_price >= 2.0 else "shield"
        else:
            prop_type = "standard"

        prop_key = (player_name, standard_market, line)
        if prop_key not in grouped_props:
            grouped_props[prop_key] = {
                "sportsbook": "Dabble",
                "player": player_name,
                "market": standard_market,
                "line": line,
                "prop_type": prop_type,
                "over_odds": None,
                "under_odds": None,
            }

        if line_type in ["over", "more"]:
            grouped_props[prop_key]["over_odds"] = american_odds
        elif line_type in ["under", "less"]:
            grouped_props[prop_key]["under_odds"] = american_odds

    return list(grouped_props.values())


async def fetch_game_props(client, game_id, bearer_token):
    """
    Fetch raw JSON for a single game and pass the root detail object to the parser.
    """
    url = DABBLE_FIXTURE_DETAIL_URL.format(game_id=game_id)
    headers = DABBLE_BASE_HEADERS.copy()
    headers["Authorization"] = f"Bearer {bearer_token}"

    try:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        sport_fixture_detail = data.get("sportFixtureDetail", {})
        parsed_props = parse_game_props(sport_fixture_detail)
        return parsed_props if parsed_props else []
    except Exception as exc:
        print(f"Failed to fetch props for game {game_id}: {exc}")
        return []


class DabbleEngine(BaseScraper):
    sportsbook_name = "Dabble"

    async def authenticate(self) -> str | None:
        return await get_fresh_token()

    async def scrape(self) -> list[dict]:
        token = await self.authenticate()
        if not token:
            logger.error("aborting: auth failed")
            return []

        game_ids = await get_all_active_game_ids(token)
        if not game_ids:
            logger.warning("slate empty: no active games")
            return []

        all_props = []
        async with httpx.AsyncClient(verify=False) as client:
            tasks = [fetch_game_props(client, game_id, token) for game_id in game_ids]
            results = await asyncio.gather(*tasks)
            for game_result in results:
                all_props.extend(game_result)

        return all_props


async def main():
    """Orchestrate the Dabble data pipeline from authentication to storage."""
    logger.info("Starting Dabble ingestion...")
    engine = DabbleEngine()
    output_path = "data/archive/dabble/dabble_master_board.json"
    props = await engine.run(output_path)
    logger.success(f"pipeline complete: saved {len(props)} props to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
