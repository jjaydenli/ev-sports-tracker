import json
from pathlib import Path

from config.fd_markets import FD_LIVE_SGP_TAB, FD_LIVE_TAB_MARKETS_BY_LEAGUE
from core.engine import build_player_market_key
from parsers.fd_parser import parse_fd_props
from parsers.normalize import normalize_platform
from scrapers.sportsbooks.fd_api import flatten_event_page_response


def test_live_fd_row_keeps_is_live_through_normalize():
    """A live FD row must key like a live Betr row (player|market|live), or it never
    matches. The engine stamps is_live on each flattened prop; normalize must keep it."""
    payload = json.loads(
        Path("tests/fixtures/fd_event_36257605_live_sgp.json").read_text(encoding="utf-8")
    )
    props = flatten_event_page_response(
        payload,
        event_id="36257605",
        tab=FD_LIVE_SGP_TAB,
        markets=set(FD_LIVE_TAB_MARKETS_BY_LEAGUE["nba"][FD_LIVE_SGP_TAB]),
        league="nba",
        is_live=True,
    )
    for prop in props:
        prop.update(league="NBA", event_start="2026-11-01T22:30:00Z", is_live=True)

    dunn = [
        row
        for row in parse_fd_props(props)
        if row["player"] == "Kris Dunn" and row["market"] == "assists"
    ]
    assert dunn
    assert {build_player_market_key(row) for row in dunn} == {"kris dunn|assists|live"}


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
            "market": "pitching_strikeouts",
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
    assert result[0]["market"] == "pitching_strikeouts"
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
                "market": "pitching_strikeouts",
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
                "market": "pitching_strikeouts",
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
