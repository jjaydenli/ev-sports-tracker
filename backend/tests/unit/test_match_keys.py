from core.line_adjustment import build_player_market_key, normalize_game_key
from core.engine import normalize_player_name


def test_normalize_game_key_uppercases():
    assert normalize_game_key("cin@nyy") == "CIN@NYY"


def test_build_player_market_key_scopes_live_snapshot():
    prop = {
        "player": "Nathaniel Lowe",
        "market": "hits",
        "game": "CIN@NYY",
        "is_live": True,
    }
    key = build_player_market_key(prop, normalize_player_name=normalize_player_name)
    assert key == "nathaniel lowe|hits|CIN@NYY|live"


def test_build_player_market_key_pregame_omits_live_suffix():
    prop = {
        "player": "Nathaniel Lowe",
        "market": "hits",
        "game": "CIN@NYY",
    }
    key = build_player_market_key(prop, normalize_player_name=normalize_player_name)
    assert key == "nathaniel lowe|hits|CIN@NYY"
