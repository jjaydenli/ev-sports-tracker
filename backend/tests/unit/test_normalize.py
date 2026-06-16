import json
from pathlib import Path

import pytest

from core.pipeline_artifacts import load_wrapped_board
from parsers.betr_parser import parse_betr_props
from parsers.dk_parser import parse_dk_props
from parsers.normalize import (
    merge_normalized,
    normalize_all,
    normalize_platform,
)


def test_normalize_platform_dispatches_to_betr_parser():
    raw_props = [
        {
            "player": "Test Player",
            "key": "POINTS",
            "type": "REGULAR",
            "value": 20.5,
            "market_id": "1",
            "allowed_options": [
                {"market_option_id": "1", "outcome": "OVER"},
                {"market_option_id": "2", "outcome": "UNDER"},
            ],
        }
    ]

    result = normalize_platform("betr", raw_props)

    assert len(result) == 1
    assert result[0]["sportsbook"] == "Betr"
    assert result[0]["market"] == "points"


def test_normalize_platform_dispatches_to_dk_parser():
    raw_props = [
        {
            "sportsbook": "DraftKings",
            "player": "Test Player",
            "market": "points",
            "line": 25.5,
            "over_odds": -110,
            "under_odds": -120,
        }
    ]

    result = normalize_platform("draftkings", raw_props)

    assert len(result) == 1
    assert result[0]["market"] == "points"
    assert result[0]["prop_type"] == "standard"


def test_merge_normalized_combines_platform_lists():
    betr_props = parse_betr_props(
        [
            {
                "player": "Player A",
                "key": "POINTS",
                "type": "REGULAR",
                "value": 10.5,
                "allowed_options": [
                    {"market_option_id": "1", "outcome": "OVER"},
                    {"market_option_id": "2", "outcome": "UNDER"},
                ],
            }
        ]
    )
    dk_props = parse_dk_props(
        [
            {
                "sportsbook": "DraftKings",
                "player": "Player B",
                "market": "assists",
                "line": 5.5,
                "over_odds": -110,
                "under_odds": -120,
            }
        ]
    )

    merged = merge_normalized([betr_props, dk_props])

    assert len(merged) == 2
    assert {prop["sportsbook"] for prop in merged} == {"Betr", "DraftKings"}


def test_normalize_platform_unknown_raises():
    with pytest.raises(ValueError, match="Unknown platform"):
        normalize_platform("unknown", [])


def test_normalize_platform_dabble_not_in_active_pipeline():
    with pytest.raises(ValueError, match="Unknown platform"):
        normalize_platform("dabble", [])


def test_normalize_all_writes_per_platform_and_unified(tmp_path):
    betr_board = [
        {
            "player": "Josh Hart",
            "key": "POINTS",
            "type": "REGULAR",
            "value": 12.5,
            "market_id": "betr-1",
            "game": "NY@CLE",
            "team": "NY",
            "allowed_options": [
                {"market_option_id": "1", "outcome": "OVER"},
                {"market_option_id": "2", "outcome": "UNDER"},
            ],
        }
    ]
    dk_board = [
        {
            "sportsbook": "DraftKings",
            "player": "Josh Hart",
            "market": "points",
            "line": 12.5,
            "over_odds": -110,
            "under_odds": -120,
        }
    ]

    (tmp_path / "betr_master_board.json").write_text(
        json.dumps(betr_board), encoding="utf-8"
    )
    (tmp_path / "dk_master_board.json").write_text(json.dumps(dk_board), encoding="utf-8")

    unified = normalize_all(tmp_path)

    assert len(unified) == 2
    _, betr_norm = load_wrapped_board(tmp_path / "betr_normalized.json")
    assert len(betr_norm) == 1
    assert (tmp_path / "dk_normalized.json").exists()
    assert (tmp_path / "unified_master_board.json").exists()
    assert not (tmp_path / "dabble_normalized.json").exists()


def test_normalize_all_skips_missing_platform_without_failing(tmp_path):
    (tmp_path / "betr_master_board.json").write_text(
        json.dumps(
            [
                {
                    "player": "Only Betr",
                    "key": "REBOUNDS",
                    "type": "REGULAR",
                    "value": 8.5,
                    "allowed_options": [
                        {"market_option_id": "1", "outcome": "MORE"},
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    unified = normalize_all(tmp_path)

    assert len(unified) == 1
    assert unified[0]["sportsbook"] == "Betr"
    assert not (tmp_path / "dk_normalized.json").exists()
