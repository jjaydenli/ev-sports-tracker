from scrapers.dfs.betr.betr_engine import extract_raw_props


def _miles_mcbride_projection(**overrides):
    base = {
        "marketId": "1032605212843962057",
        "marketStatus": "OPENED",
        "isLive": False,
        "type": "EDGE_1",
        "label": "FG Att",
        "key": "FIELD_GOALS_ATTEMPTED",
        "value": 0.5,
        "nonRegularValue": 4.5,
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
        "teams": [
            {
                "name": "NY",
                "players": [
                    {
                        "id": "648a076a6cd5e52740a3fdba",
                        "firstName": "Miles",
                        "lastName": "McBride",
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
    assert prop["market_status"] == "OPENED"
    assert prop["is_live"] is False


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
