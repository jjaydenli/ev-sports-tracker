from scrapers.sportsbooks.dk_api import (
    build_event_game_map,
    build_event_start_map,
    game_key_from_dk_event,
)


def test_game_key_from_dk_event_away_home_abbrev():
    event = {
        "participants": [
            {
                "type": "Team",
                "venueRole": "Away",
                "metadata": {"shortName": "CIN"},
            },
            {
                "type": "Team",
                "venueRole": "Home",
                "metadata": {"shortName": "NYY"},
            },
        ]
    }
    assert game_key_from_dk_event(event) == "CIN@NYY"


def test_build_event_game_map_indexes_events():
    payload = {
        "events": [
            {
                "id": "34293895",
                "participants": [
                    {
                        "type": "Team",
                        "venueRole": "Away",
                        "metadata": {"shortName": "CIN"},
                    },
                    {
                        "type": "Team",
                        "venueRole": "Home",
                        "metadata": {"shortName": "NYY"},
                    },
                ],
            },
            {"id": "999", "participants": []},
        ]
    }
    assert build_event_game_map(payload) == {"34293895": "CIN@NYY"}


def test_build_event_start_map_indexes_start_event_date():
    payload = {
        "events": [
            {
                "id": "34293895",
                "startEventDate": "2026-06-19T23:10:00.0000000Z",
            },
            {"id": "999"},
        ]
    }
    assert build_event_start_map(payload) == {
        "34293895": "2026-06-19T23:10:00.0000000Z",
    }
