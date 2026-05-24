import pytest
import httpx

from scrapers.dfs.betr.betr_api import (
    LEAGUE_UPCOMING_EVENTS_QUERY,
    fetch_league_upcoming_events,
    graphql_request,
    normalize_bearer_token,
)


def test_normalize_bearer_token_strips_bearer_prefix():
    """Betr expects the raw JWT in Authorization, not a Bearer prefix."""
    raw = "eyJhbGciOiJSUzI1NiJ9.test"
    assert normalize_bearer_token(raw) == raw
    assert normalize_bearer_token(f"Bearer {raw}") == raw
    assert normalize_bearer_token(f"bearer {raw}") == raw


@pytest.mark.asyncio
async def test_graphql_request_returns_none_on_http_error():
    """Surface API failures as None instead of raising during orchestration."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            request=request,
            text="unauthorized",
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await graphql_request(
            client,
            operation_name="LeagueUpcomingEvents",
            query=LEAGUE_UPCOMING_EVENTS_QUERY,
            variables={"league": "NBA"},
            bearer_token="test-token",
        )

    assert result is None


@pytest.mark.asyncio
async def test_fetch_league_upcoming_events_sends_league_variable():
    """Pass the league enum to LeagueUpcomingEvents."""
    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured["payload"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={"data": {"getUpcomingEventsV2": []}},
            request=request,
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await fetch_league_upcoming_events(
            "NBA", "test-token", client=client
        )

    assert result == {"data": {"getUpcomingEventsV2": []}}
    assert captured["payload"]["operationName"] == "LeagueUpcomingEvents"
    assert captured["payload"]["query"] == LEAGUE_UPCOMING_EVENTS_QUERY
    assert captured["payload"]["variables"] == {"league": "NBA"}
