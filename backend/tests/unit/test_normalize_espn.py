from parsers.espn_parser import parse_espn_props
from parsers.normalize import normalize_platform


def test_normalize_platform_dispatches_to_espn_parser():
    raw_props = [
        {
            "sportsbook": "ESPN",
            "player": "Parker Messick",
            "market": "strikeouts",
            "line": 5.5,
            "over_odds": -114,
            "under_odds": -114,
            "is_main_line": True,
            "league": "MLB",
        }
    ]
    result = normalize_platform("espn", raw_props)
    assert len(result) == 1
    assert result[0]["sportsbook"] == "ESPN"
    assert result[0]["market"] == "strikeouts"
    assert result[0]["league"] == "MLB"


def test_parse_espn_props_propagates_league_from_grouped_ladder():
    rows = parse_espn_props(
        [
            {
                "sportsbook": "ESPN",
                "player": "Parker Messick",
                "market": "strikeouts",
                "league": "MLB",
                "lines": [
                    {
                        "line": 5.5,
                        "over_odds": -114,
                        "under_odds": -114,
                        "is_main_line": True,
                    }
                ],
            }
        ]
    )
    assert len(rows) == 1
    assert rows[0]["league"] == "MLB"
