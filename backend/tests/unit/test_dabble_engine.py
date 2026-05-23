"""
Integration tests for the Dabble data ingestion layer.
Verifies coordination between raw API responses and the relational parser.
"""

import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from scrapers.dfs.dabble_engine import fetch_game_props


@pytest.mark.asyncio
async def test_fetch_game_props_success():
    """
    Verify that fetch_game_props correctly routes raw API data to the parser.

    This test mocks the httpx.AsyncClient to simulate a successful
    200 OK response from Dabble's fixture detail endpoint.
    """
    mock_game_id = "test-game-123"
    mock_token = "mock-bearer-token"

    mock_response_data = {
        "sportFixtureDetail": {
            "markets": [
                {"id": "m1", "status": "open", "isDfsAllowed": True, "resultingType": "points"}
            ],
            "prices": [{"selectionId": "s1", "marketId": "m1", "price": 1.82}],
            "playerProps": [
                {
                    "playerName": "Test Player",
                    "marketId": "m1",
                    "selectionId": "s1",
                    "value": 10.5,
                    "lineType": "over",
                }
            ],
        }
    }

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = mock_response_data
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_response

    with patch("scrapers.dfs.dabble_engine.parse_game_props") as mock_parser:
        mock_parser.return_value = [{"player": "Test Player", "over_odds": -122}]

        result = await fetch_game_props(mock_client, mock_game_id, mock_token)

        args, kwargs = mock_client.get.call_args
        assert f"sport-fixtures/details/{mock_game_id}" in args[0]
        assert f"Bearer {mock_token}" in kwargs["headers"]["Authorization"]

        mock_parser.assert_called_once_with(mock_response_data["sportFixtureDetail"])

        assert len(result) == 1
        assert result[0]["player"] == "Test Player"


@pytest.mark.asyncio
async def test_fetch_game_props_api_failure():
    """Verify that fetch_game_props handles API errors without crashing."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.side_effect = Exception("API Connection Error")

    result = await fetch_game_props(mock_client, "error-id", "token")

    assert result == []
