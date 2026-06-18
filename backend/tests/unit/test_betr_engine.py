import json
from pathlib import Path

from scrapers.dfs.betr.betr_engine import (
    BETR_LIVE_EVENT_STATUSES,
    extract_raw_props,
    iter_live_events,
    iter_scheduled_events,
)

BETR_MLB_LIVE_FIXTURE_PATH = Path("tests/fixtures/betr_mlb_live.json")
BETR_WNBA_PREGAME_FIXTURE_PATH = Path("tests/fixtures/betr_wnba_pregame.json")


def _miles_mcbride_projection(**overrides):
    base = {
        "marketId": "1032605212843962057",
        "marketStatus": "OPENED",
        "isLive": False,
        "type": "EDGE_1",
        "label": "FG Att",
        "name": "FG Att",
        "key": "FIELD_GOALS_ATTEMPTED",
        "value": 0.5,
        "nonRegularValue": 4.5,
        "nonRegularPercentage": 0,
        "order": 30,
        "currentValue": None,
        "allowedOptions": [
            {"marketOptionId": "1032605212979115285", "outcome": "MORE"},
        ],
        "playerRecentStats": {
            "averageValue": 4.2,
            "stats": [
                {
                    "value": 5.0,
                    "matchupDescription": "vs BOS",
                    "date": "2026-05-20",
                }
            ],
        },
    }
    base.update(overrides)
    return base


def _league_payload(*events):
    return {"data": {"getUpcomingEventsV2": list(events)}}


def _scheduled_event(**overrides):
    base = {
        "id": "6a0a88ac8e1ce70219715f9e",
        "name": "NY@CLE",
        "status": "SCHEDULED",
        "competitionType": "VERSUS",
        "playerStructure": "TEAM",
        "dataFeedSourceIds": [{"id": "13916387", "source": "BET_GENIUS"}],
        "venueDetails": {"name": "Rocket Arena", "city": "Cleveland", "country": "USA"},
        "attributes": [],
        "teams": [
            {
                "id": "648a048be70ced3cb8eba364",
                "name": "NY",
                "league": "NBA",
                "sport": "BASKETBALL",
                "players": [
                    {
                        "id": "648a076a6cd5e52740a3fdba",
                        "firstName": "Miles",
                        "lastName": "McBride",
                        "position": "PG",
                        "jerseyNumber": 2,
                        "attributes": [],
                        "projections": [_miles_mcbride_projection()],
                    }
                ],
            }
        ],
    }
    base.update(overrides)
    return base


def test_extract_raw_props_returns_raw_fields():
    """Verify LeagueUpcomingEvents payloads emit raw projection fields."""
    result = extract_raw_props(_league_payload(_scheduled_event()))

    assert len(result) == 1
    prop = result[0]
    assert prop["market_id"] == "1032605212843962057"
    assert prop["event_id"] == "6a0a88ac8e1ce70219715f9e"
    assert prop["game"] == "NY@CLE"
    assert prop["team"] == "NY"
    assert prop["player_id"] == "648a076a6cd5e52740a3fdba"
    assert prop["player"] == "Miles McBride"
    assert prop["label"] == "FG Att"
    assert prop["key"] == "FIELD_GOALS_ATTEMPTED"
    assert prop["type"] == "EDGE_1"
    assert prop["value"] == 0.5
    assert prop["non_regular_value"] == 4.5
    assert prop["non_regular_percentage"] == 0
    assert prop["order"] == 30
    assert prop["current_value"] is None
    assert prop["allowed_options"] == [
        {"market_option_id": "1032605212979115285", "outcome": "MORE"},
    ]
    assert prop["player_recent_stats"]["average_value"] == 4.2
    assert prop["competition_type"] == "VERSUS"
    assert prop["data_feed_source_ids"] == [{"id": "13916387", "source": "BET_GENIUS"}]
    assert prop["venue_details"]["city"] == "Cleveland"
    assert prop["jersey_number"] == 2
    assert prop["team_league"] == "NBA"
    assert prop["market_status"] == "OPENED"
    assert prop["is_live"] is False


def test_extract_raw_props_includes_league_and_event_status():
    result = extract_raw_props(_league_payload(_scheduled_event()), league="MLB")
    assert len(result) == 1
    assert result[0]["league"] == "MLB"
    assert result[0]["event_status"] == "SCHEDULED"


def test_extract_raw_props_skips_in_progress_events():
    """Verify only SCHEDULED events contribute props."""
    payload = _league_payload(
        _scheduled_event(),
        {
            "id": "6a07fb1f59e693cc669ac38e",
            "name": "LAL@BOS",
            "status": "IN_PROGRESS",
            "teams": [
                {
                    "name": "LAL",
                    "players": [
                        {
                            "id": "player-2",
                            "firstName": "LeBron",
                            "lastName": "James",
                            "projections": [
                                _miles_mcbride_projection(marketId="999")
                            ],
                        }
                    ],
                }
            ],
        },
    )

    result = extract_raw_props(payload)

    assert len(result) == 1
    assert result[0]["player"] == "Miles McBride"


def test_extract_raw_props_skips_suspended_and_live_projections():
    """Verify OPENED and not-live filters exclude bad projections."""
    payload = _league_payload(
        _scheduled_event(
            teams=[
                {
                    "name": "NY",
                    "players": [
                        {
                            "id": "648a076a6cd5e52740a3fdba",
                            "firstName": "Miles",
                            "lastName": "McBride",
                            "projections": [
                                _miles_mcbride_projection(),
                                _miles_mcbride_projection(
                                    marketId="102",
                                    marketStatus="SUSPENDED",
                                ),
                                _miles_mcbride_projection(
                                    marketId="103",
                                    isLive=True,
                                ),
                            ],
                        }
                    ],
                }
            ]
        )
    )

    result = extract_raw_props(payload)

    assert len(result) == 1
    assert result[0]["market_id"] == "1032605212843962057"


def test_extract_raw_props_deduplicates_market_ids():
    """Verify duplicate marketId values are only emitted once."""
    duplicate_projection = _miles_mcbride_projection()
    payload = _league_payload(
        _scheduled_event(
            teams=[
                {
                    "name": "NY",
                    "players": [
                        {
                            "id": "648a076a6cd5e52740a3fdba",
                            "firstName": "Miles",
                            "lastName": "McBride",
                            "projections": [duplicate_projection, duplicate_projection],
                        }
                    ],
                }
            ]
        )
    )

    result = extract_raw_props(payload)

    assert len(result) == 1


def test_extract_raw_props_handles_empty_payload():
    """Verify the extractor returns safely when the payload is missing or empty."""
    assert extract_raw_props({}) == []
    assert extract_raw_props({"data": {"getUpcomingEventsV2": None}}) == []
    assert extract_raw_props({"data": {"getUpcomingEventsV2": []}}) == []


def _live_event(**overrides):
    base = {
        "id": "live-event-001",
        "name": "NYM@LAD",
        "status": "IN_PROGRESS",
        "competitionType": "VERSUS",
        "playerStructure": "TEAM",
        "dataFeedSourceIds": [],
        "venueDetails": None,
        "attributes": [],
        "teams": [
            {
                "name": "NYM",
                "league": "MLB",
                "sport": "BASEBALL",
                "players": [
                    {
                        "id": "player-lindor",
                        "firstName": "Francisco",
                        "lastName": "Lindor",
                        "projections": [
                            _miles_mcbride_projection(
                                marketId="live-market-001",
                                marketStatus="OPENED",
                                isLive=True,
                                type="REGULAR",
                                key="HITS",
                                label="Hits",
                                value=1.5,
                                allowedOptions=[
                                    {"marketOptionId": "o1", "outcome": "OVER"},
                                    {"marketOptionId": "o2", "outcome": "UNDER"},
                                ],
                            )
                        ],
                    }
                ],
            }
        ],
    }
    base.update(overrides)
    return base


def test_betr_live_event_statuses_constant():
    assert "IN_PROGRESS" in BETR_LIVE_EVENT_STATUSES


def test_iter_live_events_yields_in_progress():
    payload = _league_payload(_scheduled_event(), _live_event())
    live = list(iter_live_events(payload))
    assert len(live) == 1
    assert live[0]["status"] == "IN_PROGRESS"


def test_iter_scheduled_events_excludes_in_progress():
    payload = _league_payload(_scheduled_event(), _live_event())
    scheduled = list(iter_scheduled_events(payload))
    assert len(scheduled) == 1
    assert scheduled[0]["status"] == "SCHEDULED"


def test_extract_raw_props_includes_live_events():
    """IN_PROGRESS events with isLive=True projections are included."""
    payload = _league_payload(_scheduled_event(), _live_event())
    result = extract_raw_props(payload)
    assert len(result) == 2
    live_props = [p for p in result if p["is_live"] is True]
    pregame_props = [p for p in result if not p["is_live"]]
    assert len(live_props) == 1
    assert len(pregame_props) == 1
    assert live_props[0]["market_id"] == "live-market-001"


def test_extract_raw_props_live_event_status_set():
    payload = _league_payload(_live_event())
    result = extract_raw_props(payload)
    assert len(result) == 1
    assert result[0]["event_status"] == "IN_PROGRESS"
    assert result[0]["is_live"] is True


def test_extract_raw_props_betr_mlb_live_fixture():
    payload = json.loads(BETR_MLB_LIVE_FIXTURE_PATH.read_text(encoding="utf-8"))
    result = extract_raw_props(payload, league="MLB")
    assert len(result) == 1
    prop = result[0]
    assert prop["is_live"] is True
    assert prop["event_status"] == "IN_PROGRESS"
    assert prop["key"] == "HITS"
    assert prop["value"] == 1.5
    assert prop["market_id"] == "live-market-hits-001"
    assert prop["player"] == "Francisco Lindor"


def test_extract_raw_props_live_projection_in_scheduled_event_excluded():
    """isLive=True projection inside a SCHEDULED event is still excluded."""
    payload = _league_payload(
        _scheduled_event(
            teams=[
                {
                    "name": "NY",
                    "players": [
                        {
                            "id": "p1",
                            "firstName": "Miles",
                            "lastName": "McBride",
                            "projections": [
                                _miles_mcbride_projection(marketId="live-in-scheduled", isLive=True),
                            ],
                        }
                    ],
                }
            ]
        )
    )
    result = extract_raw_props(payload)
    assert result == []


def test_extract_raw_props_betr_wnba_pregame_fixture():
    payload = json.loads(BETR_WNBA_PREGAME_FIXTURE_PATH.read_text(encoding="utf-8"))
    result = extract_raw_props(payload, league="WNBA")
    assert len(result) == 2
    assert all(prop["league"] == "WNBA" for prop in result)
    markets = {prop["key"] for prop in result}
    assert markets == {"POINTS", "REBOUNDS"}
    assert result[0]["player"] == "Sabrina Ionescu"
