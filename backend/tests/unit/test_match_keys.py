from core.ladder_index import (
    build_match_context_key,
    build_player_market_key,
)
from core.engine import normalize_player_name


def test_dk_deviating_abbrev_props_match_via_event_hour():
    # Abbreviation vocabulary differs (betr CHW vs DK CWS) but the gate is the
    # event-hour, so the two rows collide on the same key and match.
    betr = {
        "player": "Luis Robert",
        "market": "hits",
        "league": "MLB",
        "game": "CLE@CHW",
        "event_start": "2026-06-20T02:10:00.000Z",
    }
    dk = {
        "player": "Luis Robert",
        "market": "hits",
        "league": "MLB",
        "game": "CLE@CWS",
        "event_start": "2026-06-20T02:10:00.000Z",
    }
    assert build_match_context_key(
        betr, normalize_player_name=normalize_player_name
    ) == build_match_context_key(dk, normalize_player_name=normalize_player_name)
    assert build_player_market_key(
        betr, normalize_player_name=normalize_player_name
    ) == build_player_market_key(dk, normalize_player_name=normalize_player_name)


def test_build_player_market_key_scopes_live_snapshot():
    prop = {
        "player": "Nathaniel Lowe",
        "market": "hits",
        "game": "CIN@NYY",
        "event_start": "2026-06-20T02:10:00.000Z",
        "is_live": True,
    }
    key = build_player_market_key(prop, normalize_player_name=normalize_player_name)
    assert key == "nathaniel lowe|hits|live"


def test_build_player_market_key_pregame_omits_live_suffix():
    prop = {
        "player": "Nathaniel Lowe",
        "market": "hits",
        "game": "CIN@NYY",
        "event_start": "2026-06-20T02:10:00.000Z",
    }
    key = build_player_market_key(prop, normalize_player_name=normalize_player_name)
    assert key == "nathaniel lowe|hits|2026-06-20T02"


def test_build_player_market_key_different_hours_do_not_collide():
    early = {
        "player": "Nathaniel Lowe",
        "market": "hits",
        "game": "CIN@NYY",
        "event_start": "2026-06-19T17:05:00.000Z",
    }
    late = {
        "player": "Nathaniel Lowe",
        "market": "hits",
        "game": "CIN@NYY",
        "event_start": "2026-06-19T23:10:00.000Z",
    }
    assert build_player_market_key(
        early, normalize_player_name=normalize_player_name
    ) != build_player_market_key(late, normalize_player_name=normalize_player_name)


def test_build_match_context_key_includes_league_and_event_hour():
    prop = {
        "player": "Freddie Freeman",
        "market": "total_bases",
        "league": "MLB",
        "game": "BAL@LAD",
        "event_start": "2026-06-20T02:10:00.000Z",
    }
    key = build_match_context_key(prop, normalize_player_name=normalize_player_name)
    assert key == "freddie freeman|total_bases|MLB|2026-06-20T02"


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
    assert key == "nathaniel lowe|hits|MLB|live"


def test_build_match_context_key_live_omits_hour_when_books_disagree():
    """Live rows skip event_hour so Betr scheduled time can match DK actual start."""
    betr = {
        "player": "Bo Bichette",
        "market": "h+r+rbi",
        "league": "MLB",
        "game": "PHI@NYM",
        "event_start": "2026-06-27T20:10Z",
        "is_live": True,
    }
    dk = {
        "player": "Bo Bichette",
        "market": "h+r+rbi",
        "league": "MLB",
        "game": "PHI@NYM",
        "event_start": "2026-06-27T21:20:07.0000000Z",
        "is_live": True,
    }
    betr_key = build_match_context_key(betr, normalize_player_name=normalize_player_name)
    dk_key = build_match_context_key(dk, normalize_player_name=normalize_player_name)
    assert betr_key == dk_key == "bo bichette|h+r+rbi|MLB|live"
