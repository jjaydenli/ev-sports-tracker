"""
Module: test_dabble_parser.py
Description: Unit tests for the Dabble ingestion engine's parsing logic.
             Ensures relational linking, edge cases, and promo classifications
             (Lightnings/Shields) are completely accurate.
"""

from scrapers.dfs.dabble_engine import parse_game_props


def test_parse_game_props_classification_and_regression(mock_standard_and_promo_payload):
    """
    Validates that standard props group correctly and promos (Lightnings/Shields)
    trigger the regression fix ensuring missing sides default to None.
    """
    results = parse_game_props(mock_standard_and_promo_payload)

    assert len(results) == 3, f"Expected 3 unique props, got {len(results)}"

    standard_prop = next(prop for prop in results if prop["player"] == "Standard Player")
    lightning_prop = next(prop for prop in results if prop["player"] == "Lightning Player")
    shield_prop = next(prop for prop in results if prop["player"] == "Shield Player")

    assert standard_prop["prop_type"] == "standard"
    assert standard_prop["over_odds"] == -122
    assert standard_prop["under_odds"] == -122

    assert lightning_prop["prop_type"] == "lightning"
    assert lightning_prop["over_odds"] == 150
    assert lightning_prop["under_odds"] is None

    assert shield_prop["prop_type"] == "shield"
    assert shield_prop["over_odds"] == -154
    assert shield_prop["under_odds"] is None


def test_parse_game_props_edge_cases():
    """
    Ensures the parser handles malformed or empty payloads without crashing and
    correctly filters props linked to non-open or suspended markets.
    """
    assert parse_game_props({}) == [], "Failed on completely empty payload."

    # missing prices array should still group the prop with unset odds
    no_prices_payload = {
        "markets": [
            {"id": "m1", "status": "open", "isDfsAllowed": True, "resultingType": "points"}
        ],
        "playerProps": [
            {
                "playerName": "Ghost Player",
                "marketId": "m1",
                "selectionId": "missing_sel",
                "value": 10.5,
                "lineType": "over",
            }
        ],
    }

    missing_price_results = parse_game_props(no_prices_payload)
    assert len(missing_price_results) == 1, "Failed to parse prop when prices array is missing."
    assert missing_price_results[0]["over_odds"] is None, "Failed to leave odds unset when price is missing."
    assert missing_price_results[0]["under_odds"] is None, "Failed missing under_odds None check."

    closed_market_payload = {
        "markets": [
            {"id": "m_closed", "status": "suspended", "isDfsAllowed": True, "resultingType": "points"}
        ],
        "playerProps": [
            {
                "playerName": "Banned Player",
                "marketId": "m_closed",
                "selectionId": "sel1",
                "value": 15.5,
                "lineType": "over",
            }
        ],
    }

    assert parse_game_props(closed_market_payload) == [], "Failed to filter out suspended/closed markets."
