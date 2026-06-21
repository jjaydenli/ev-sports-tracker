from core.line_adjustment import (
    build_match_context_key,
    build_player_market_key,
    normalize_game_key,
)
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


def test_build_match_context_key_includes_league_and_event_hour():
    prop = {
        "player": "Freddie Freeman",
        "market": "total_bases",
        "league": "MLB",
        "game": "BAL@LAD",
        "event_start": "2026-06-20T02:10:00.000Z",
    }
    key = build_match_context_key(prop, normalize_player_name=normalize_player_name)
    assert key == "freddie freeman|total_bases|MLB|BAL@LAD|2026-06-20T02"


def test_build_match_context_key_hour_floor_absorbs_minute_drift():
    betr = {
        "player": "Test Player",
        "market": "hits",
        "event_start": "2026-06-19T17:05:00.000Z",
    }
    dk = {
        "player": "Test Player",
        "market": "hits",
        "event_start": "2026-06-19T17:40:00.000Z",
    }
    betr_key = build_match_context_key(betr, normalize_player_name=normalize_player_name)
    dk_key = build_match_context_key(dk, normalize_player_name=normalize_player_name)
    assert betr_key == dk_key == "test player|hits|2026-06-19T17"


def test_build_match_context_key_separates_doubleheader_games():
    game1 = {
        "player": "Test Player",
        "market": "hits",
        "game": "CIN@NYY",
        "event_start": "2026-06-19T17:05:00.000Z",
    }
    game2 = {
        "player": "Test Player",
        "market": "hits",
        "game": "CIN@NYY",
        "event_start": "2026-06-19T23:10:00.000Z",
    }
    key1 = build_match_context_key(game1, normalize_player_name=normalize_player_name)
    key2 = build_match_context_key(game2, normalize_player_name=normalize_player_name)
    assert key1 != key2


def test_build_match_context_key_live_without_event_start():
    prop = {
        "player": "Nathaniel Lowe",
        "market": "hits",
        "league": "MLB",
        "game": "CIN@NYY",
        "is_live": True,
    }
    key = build_match_context_key(prop, normalize_player_name=normalize_player_name)
    assert key == "nathaniel lowe|hits|MLB|CIN@NYY|live"
