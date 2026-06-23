from parsers.fd_parser import parse_fd_props
from parsers.normalize import normalize_platform


def test_normalize_platform_dispatches_to_fd_parser():
    raw_props = [
        {
            "sportsbook": "FanDuel",
            "player": "Victor Wembanyama",
            "market": "points",
            "line": 25.5,
            "over_odds": -114,
            "under_odds": -114,
            "is_main_line": True,
        }
    ]

    result = normalize_platform("fanduel", raw_props)

    assert len(result) == 1
    assert result[0]["market"] == "points"
    assert result[0]["sportsbook"] == "FanDuel"


def test_normalize_platform_mlb_strikeouts():
    raw_props = [
        {
            "sportsbook": "FanDuel",
            "player": "Parker Messick",
            "market": "strikeouts",
            "line": 5.5,
            "over_odds": -114,
            "under_odds": -114,
            "line_kind": "ou",
            "league": "MLB",
            "is_main_line": True,
        }
    ]

    result = normalize_platform("fanduel", raw_props)

    assert len(result) == 1
    assert result[0]["market"] == "strikeouts"
    assert result[0]["league"] == "MLB"
    assert result[0]["line_kind"] == "ou"


def test_parse_fd_props_preserves_alt_line_flag():
    rows = parse_fd_props(
        [
            {
                "sportsbook": "FanDuel",
                "player": "Victor Wembanyama",
                "market": "points",
                "lines": [
                    {
                        "line": 22.5,
                        "over_odds": -110,
                        "under_odds": -110,
                        "is_main_line": False,
                    }
                ],
            }
        ]
    )
    assert rows[0]["is_main_line"] is False


def test_parse_fd_props_propagates_league_from_grouped_ladder():
    """Grouped master-board rows carry league on the parent, not each line entry."""
    rows = parse_fd_props(
        [
            {
                "sportsbook": "FanDuel",
                "player": "Parker Messick",
                "market": "strikeouts",
                "line_kind": "ou",
                "league": "MLB",
                "event_id": "35730475",
                "tab": "pitcher-props",
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
    assert rows[0]["line_kind"] == "ou"


def test_parse_fd_props_propagates_game_from_grouped_ladder():
    """The cross-book ``game`` stamped by the engine survives grouped expansion."""
    rows = parse_fd_props(
        [
            {
                "sportsbook": "FanDuel",
                "player": "Parker Messick",
                "market": "strikeouts",
                "line_kind": "ou",
                "league": "MLB",
                "game": "CLE@MIL",
                "event_id": "35730475",
                "tab": "pitcher-props",
                "lines": [
                    {"line": 5.5, "over_odds": -114, "under_odds": -114},
                ],
            }
        ]
    )
    assert rows[0]["game"] == "CLE@MIL"


def test_parse_fd_props_milestone_fields_survive_normalization():
    grouped = [
        {
            "sportsbook": "FanDuel",
            "player": "Vladimir Guerrero Jr.",
            "market": "total_bases",
            "line_kind": "milestone",
            "league": "MLB",
            "lines": [
                {
                    "line": 1.5,
                    "milestone_threshold": 2,
                    "over_odds": 120,
                    "under_odds": None,
                    "is_main_line": False,
                    "market_type": "TO_RECORD_2+_TOTAL_BASES",
                }
            ],
        }
    ]
    rows = parse_fd_props(grouped)
    assert len(rows) == 1
    assert rows[0]["line_kind"] == "milestone"
    assert rows[0]["milestone_threshold"] == 2
    assert rows[0]["under_odds"] is None

    normalized = normalize_platform("fanduel", grouped)
    assert normalized[0]["line_kind"] == "milestone"
    assert normalized[0]["milestone_threshold"] == 2
    assert normalized[0]["under_odds"] is None
