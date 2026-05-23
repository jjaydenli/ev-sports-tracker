"""Shared fixtures and mock HTTP responses."""

import pytest


@pytest.fixture
def mock_standard_and_promo_payload():
    """
    Provides a static, mocked Dabble JSON payload.
    Contains one standard two-way prop, one Lightning prop, and one Shield prop.
    """
    return {
        "markets": [
            {"id": "m_points", "status": "open", "isDfsAllowed": True, "resultingType": "points"},
            {"id": "m_assists", "status": "open", "isDfsAllowed": True, "resultingType": "assists"},
            {"id": "m_rebounds", "status": "open", "isDfsAllowed": True, "resultingType": "rebounds"},
        ],
        "prices": [
            {"selectionId": "sel_s_over", "marketId": "m_points", "price": 1.82},
            {"selectionId": "sel_s_under", "marketId": "m_points", "price": 1.82},
            {"selectionId": "sel_l_over", "marketId": "m_assists", "price": 2.50},
            {"selectionId": "sel_sh_over", "marketId": "m_rebounds", "price": 1.65},
        ],
        "playerProps": [
            {
                "playerName": "Standard Player",
                "marketId": "m_points",
                "selectionId": "sel_s_over",
                "value": 20.5,
                "lineType": "over",
            },
            {
                "playerName": "Standard Player",
                "marketId": "m_points",
                "selectionId": "sel_s_under",
                "value": 20.5,
                "lineType": "under",
            },
            {
                "playerName": "Lightning Player",
                "marketId": "m_assists",
                "selectionId": "sel_l_over",
                "value": 5.5,
                "lineType": "over",
            },
            {
                "playerName": "Shield Player",
                "marketId": "m_rebounds",
                "selectionId": "sel_sh_over",
                "value": 10.5,
                "lineType": "over",
            },
        ],
    }
