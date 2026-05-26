"""Betr GraphQL client for LeagueUpcomingEvents requests."""

from typing import Any

import httpx
from loguru import logger

from config.api_headers import BETR_BASE_HEADERS, BETR_GRAPHQL_URL

LEAGUE_UPCOMING_EVENTS_QUERY = """
query LeagueUpcomingEvents($league: League!) {
  getUpcomingEventsV2(league: $league) {
    id
    name
    sport
    league
    status
    date
    competitionType
    playerStructure
    dataFeedSourceIds {
      id
      source
    }
    venueDetails {
      name
      city
      country
    }
    attributes {
      key
      value
    }
    ... on TeamVersusEvent {
      teams {
        id
        name
        league
        sport
        players {
          id
          firstName
          lastName
          position
          jerseyNumber
          attributes {
            key
            value
          }
          projections {
            marketId
            marketStatus
            isLive
            type
            label
            name
            key
            value
            nonRegularValue
            nonRegularPercentage
            order
            currentValue
            allowedOptions {
              marketOptionId
              outcome
            }
            playerRecentStats {
              averageValue
              stats {
                value
                matchupDescription
                date
              }
            }
          }
        }
      }
    }
  }
}
"""


def normalize_bearer_token(token: str) -> str:
    """Return the raw JWT for Betr's Authorization header (no Bearer prefix)."""
    token = token.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    return token


def build_betr_headers(bearer_token: str) -> dict[str, str]:
    """Return request headers with the injected bearer token."""
    headers = BETR_BASE_HEADERS.copy()
    headers["authorization"] = normalize_bearer_token(bearer_token)
    return headers


async def graphql_request(
    client: httpx.AsyncClient,
    *,
    operation_name: str,
    query: str,
    variables: dict[str, Any] | None = None,
    bearer_token: str,
) -> dict[str, Any] | None:
    """Execute a GraphQL request and return the parsed JSON body."""
    payload = {
        "operationName": operation_name,
        "query": query,
        "variables": variables or {},
    }

    try:
        response = await client.post(
            BETR_GRAPHQL_URL,
            json=payload,
            headers=build_betr_headers(bearer_token),
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:500]
        logger.error(
            f"betr api blocked request: {exc.response.status_code} — {body}"
        )
        return None
    except httpx.RequestError as exc:
        logger.error(f"betr api request failed: {exc}")
        return None


async def fetch_league_upcoming_events(
    league: str,
    bearer_token: str,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any] | None:
    """Fetch scheduled team events and player projections for one league."""
    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient()

    try:
        return await graphql_request(
            client,
            operation_name="LeagueUpcomingEvents",
            query=LEAGUE_UPCOMING_EVENTS_QUERY,
            variables={"league": league},
            bearer_token=bearer_token,
        )
    finally:
        if owns_client:
            await client.aclose()


async def main(league: str = "NBA") -> None:
    """Fetch and print a summary of LeagueUpcomingEvents (standalone debug entrypoint)."""
    import asyncio
    import json
    from pathlib import Path

    from config.settings import BETR_BEARER_TOKEN
    from scrapers.dfs.betr.betr_auth import BetrAuthError, ensure_betr_token

    try:
        token = await ensure_betr_token()
    except BetrAuthError as exc:
        logger.error(str(exc))
        return

    if not token and not BETR_BEARER_TOKEN:
        logger.error("missing Betr credentials in config/.env")
        return

    logger.info(f"fetching LeagueUpcomingEvents for {league}...")
    raw_json = await fetch_league_upcoming_events(league, token)

    if not raw_json:
        logger.error("request failed — check token and headers")
        return

    events = raw_json.get("data", {}).get("getUpcomingEventsV2") or []
    scheduled = [event for event in events if event.get("status") == "SCHEDULED"]

    projection_count = 0
    market_ids: set[str] = set()
    for event in scheduled:
        for team in event.get("teams") or []:
            for player in team.get("players") or []:
                for projection in player.get("projections") or []:
                    projection_count += 1
                    market_id = projection.get("marketId")
                    if market_id:
                        market_ids.add(market_id)

    logger.info(
        f"events={len(events)} scheduled={len(scheduled)} "
        f"projections={projection_count} unique_market_ids={len(market_ids)}"
    )

    for event in scheduled[:3]:
        logger.info(
            f"  {event.get('name')} ({event.get('status')}) id={event.get('id')}"
        )

    output_path = Path("data/processed/betr_league_upcoming_events_raw.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(raw_json, indent=2), encoding="utf-8")
    logger.success(f"saved raw response to {output_path}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
