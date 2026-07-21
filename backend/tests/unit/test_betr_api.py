import httpx
import pytest

from scrapers.dfs.betr.betr_api import (
    BETR_GRAPHQL_MAX_ATTEMPTS,
    BETR_GRAPHQL_RETRY_STATUS,
    LEAGUE_UPCOMING_EVENTS_QUERY,
    fetch_league_upcoming_events,
    graphql_request,
    normalize_bearer_token,
)

SUCCESS_BODY = {"data": {"getUpcomingEventsV2": []}}


@pytest.fixture
def no_retry_sleep(monkeypatch):
    """Collapse retry backoff so retry tests do not wait real seconds."""
    slept: list[float] = []

    async def fake_sleep(delay: float) -> None:
        slept.append(delay)

    monkeypatch.setattr("scrapers.dfs.betr.betr_api.asyncio.sleep", fake_sleep)
    return slept


async def _request(client: httpx.AsyncClient):
    return await graphql_request(
        client,
        operation_name="LeagueUpcomingEvents",
        query=LEAGUE_UPCOMING_EVENTS_QUERY,
        variables={"league": "NBA"},
        bearer_token="test-token",
    )


_REQUIRED_RETRY_STATUS = {
    429: "rate limit; concurrent league scrapes can burst past the quota",
    502: "bad gateway; the edge returns this while the origin restarts",
    503: "service unavailable; a repeat request can still succeed",
    504: "gateway timeout; upstream was slow but the request is still valid",
}


@pytest.mark.parametrize("status, reason", sorted(_REQUIRED_RETRY_STATUS.items()))
def test_retry_status_set_covers_required_transient_codes(status, reason):
    """Pin the transient codes; the behavior tests derive from this same set."""
    assert status in BETR_GRAPHQL_RETRY_STATUS, reason


def test_normalize_bearer_token_strips_bearer_prefix():
    """Betr expects the raw JWT in Authorization, not a Bearer prefix."""
    raw = "eyJhbGciOiJSUzI1NiJ9.test"
    assert normalize_bearer_token(raw) == raw
    assert normalize_bearer_token(f"Bearer {raw}") == raw
    assert normalize_bearer_token(f"bearer {raw}") == raw


@pytest.mark.asyncio
async def test_graphql_request_retries_transient_request_error(no_retry_sleep):
    """Retry transient network failures before giving up."""
    attempts = {"count": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise httpx.ConnectError("simulated transient failure", request=request)
        return httpx.Response(200, json=SUCCESS_BODY, request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await _request(client)

    assert result == SUCCESS_BODY
    assert attempts["count"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("status", sorted(BETR_GRAPHQL_RETRY_STATUS))
async def test_graphql_request_retries_transient_status(status, no_retry_sleep):
    """A transient HTTP status is retried and the recovered body is returned."""
    attempts = {"count": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 2:
            return httpx.Response(status, text="transient", request=request)
        return httpx.Response(200, json=SUCCESS_BODY, request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await _request(client)

    assert result == SUCCESS_BODY
    assert attempts["count"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_mode", ["connect_error", "persistent_503"])
async def test_graphql_request_gives_up_after_max_attempts(failure_mode, no_retry_sleep):
    """Both retry paths stop at the attempt budget and return None rather than hanging."""
    attempts = {"count": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if failure_mode == "connect_error":
            raise httpx.ConnectError("always down", request=request)
        return httpx.Response(503, text="always unavailable", request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await _request(client)

    assert result is None
    assert attempts["count"] == BETR_GRAPHQL_MAX_ATTEMPTS
    assert len(no_retry_sleep) == BETR_GRAPHQL_MAX_ATTEMPTS - 1


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
