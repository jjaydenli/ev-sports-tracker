from parsers.betr_parser import parse_betr_prop, parse_betr_props


def _both_sides_options():
    return [
        {"market_option_id": "opt-over", "outcome": "OVER"},
        {"market_option_id": "opt-under", "outcome": "UNDER"},
    ]


def _raw_betr_prop(**overrides):
    base = {
        "market_id": "1032605212843962057",
        "event_id": "6a0a88ac8e1ce70219715f9e",
        "game": "NY@CLE",
        "team": "NY",
        "player_id": "648a076a6cd5e52740a3fdba",
        "player": "Miles McBride",
        "label": "FG Att",
        "key": "FIELD_GOALS_ATTEMPTED",
        "type": "REGULAR",
        "value": 4.5,
        "non_regular_value": 0.0,
        "market_status": "OPENED",
        "is_live": False,
        "allowed_options": _both_sides_options(),
    }
    base.update(overrides)
    return base


def test_parse_betr_prop_mlb_hits():
    result = parse_betr_prop(
        _raw_betr_prop(
            league="MLB",
            key="HITS",
            label="Hits",
            value=1.5,
        )
    )
    assert result is not None
    assert result["market"] == "hits"
    assert result["league"] == "MLB"
    assert result["line"] == 1.5


def test_parse_betr_prop_mlb_total_bases():
    result = parse_betr_prop(
        _raw_betr_prop(
            league="MLB",
            key="TOTAL_BASES",
            label="Total Bases",
            value=1.5,
        )
    )
    assert result is not None
    assert result["market"] == "total_bases"


def test_parse_betr_prop_mlb_singles():
    result = parse_betr_prop(
        _raw_betr_prop(
            league="MLB",
            key="SINGLES",
            label="Singles",
            value=0.5,
        )
    )
    assert result is not None
    assert result["market"] == "singles"


def test_parse_betr_prop_mlb_doubles():
    result = parse_betr_prop(
        _raw_betr_prop(
            league="MLB",
            key="DOUBLES",
            label="Doubles",
            value=0.5,
        )
    )
    assert result is not None
    assert result["market"] == "doubles"


def test_parse_betr_prop_mlb_skips_deferred_hitter_strikeouts():
    assert (
        parse_betr_prop(
            _raw_betr_prop(
                league="MLB",
                key="HITTER_STRIKEOUTS",
                label="Strikeouts",
                value=0.5,
            )
        )
        is None
    )


def test_parse_betr_prop_regular_projection():
    result = parse_betr_prop(_raw_betr_prop())

    assert result == {
        "sportsbook": "Betr",
        "player": "Miles McBride",
        "market": "fg_attempted",
        "line": 4.5,
        "line_kind": "half_point",
        "prop_type": "standard",
        "over_odds": -120,
        "under_odds": -120,
        "raw_multiplier": None,
        "source_market_id": "1032605212843962057",
        "game": "NY@CLE",
        "team": "NY",
    }


def test_parse_betr_prop_more_only_allows_over():
    result = parse_betr_prop(
        _raw_betr_prop(
            allowed_options=[
                {"market_option_id": "opt-more", "outcome": "MORE"},
            ]
        )
    )

    assert result is not None
    assert result["over_odds"] == -120
    assert result["under_odds"] is None


def test_parse_betr_prop_less_only_allows_under():
    result = parse_betr_prop(
        _raw_betr_prop(
            allowed_options=[
                {"market_option_id": "opt-less", "outcome": "LESS"},
            ]
        )
    )

    assert result is not None
    assert result["over_odds"] is None
    assert result["under_odds"] == -120


def test_parse_betr_prop_skips_empty_allowed_options():
    assert parse_betr_prop(_raw_betr_prop(allowed_options=[])) is None


def test_parse_betr_prop_skips_edge_and_boosted_types():
    assert parse_betr_prop(_raw_betr_prop(type="EDGE_1")) is None
    assert parse_betr_prop(_raw_betr_prop(type="BOOSTED")) is None
    assert parse_betr_prop(_raw_betr_prop(type="SUPER_BOOSTED")) is None


def test_parse_betr_prop_skips_missing_player_or_value():
    assert parse_betr_prop(_raw_betr_prop(player="")) is None
    assert parse_betr_prop(_raw_betr_prop(value=None)) is None


def test_parse_betr_prop_falls_back_to_label_when_key_missing():
    result = parse_betr_prop(
        _raw_betr_prop(key=None, label="Pts+Reb", value=19.5)
    )

    assert result is not None
    assert result["market"] == "pts+reb"
    assert result["line"] == 19.5


def test_parse_betr_props_maps_all_live_board_keys():
    key_to_market = {
        "ASSISTS": "assists",
        "ASSISTS_REBOUNDS": "reb+ast",
        "BLOCKS": "blocks",
        "FANTASY_POINTS": "fantasy_pts",
        "FIELD_GOALS_ATTEMPTED": "fg_attempted",
        "FIELD_GOALS_MADE": "fg_made",
        "FOULS": "fouls",
        "FREE_THROWS_ATTEMPTED": "ft_attempted",
        "FREE_THROWS_MADE": "ft_made",
        "POINTS": "points",
        "POINTS_ASSISTS": "pts+ast",
        "POINTS_REBOUNDS": "pts+reb",
        "POINTS_REBOUNDS_ASSISTS": "pra",
        "REBOUNDS": "rebounds",
        "STEALS": "steals",
        "STEALS_BLOCKS": "stl+blk",
        "THREE_POINTERS_ATTEMPTED": "3pt_att",
        "THREE_POINTERS_MADE": "threes",
        "TURNOVERS": "turnovers",
    }

    raw_props = [
        _raw_betr_prop(key=key, label=key, value=1.5, market_id=f"id-{key}")
        for key in key_to_market
    ]

    results = parse_betr_props(raw_props)

    assert len(results) == len(key_to_market)
    for prop in results:
        raw_key = next(
            key for key, market in key_to_market.items() if f"id-{key}" == prop["source_market_id"]
        )
        assert prop["market"] == key_to_market[raw_key]


def test_parse_betr_props_filters_non_regular_from_batch():
    raw_props = [
        _raw_betr_prop(type="REGULAR", market_id="regular-1"),
        _raw_betr_prop(type="EDGE_1", market_id="edge-1"),
    ]

    results = parse_betr_props(raw_props)

    assert len(results) == 1
    assert results[0]["source_market_id"] == "regular-1"


def test_parse_betr_prop_is_live_propagates():
    result = parse_betr_prop(_raw_betr_prop(is_live=True, league="MLB", key="HITS", value=1.5))
    assert result is not None
    assert result["is_live"] is True


def test_parse_betr_prop_is_live_absent_when_false():
    result = parse_betr_prop(_raw_betr_prop(is_live=False))
    assert result is not None
    assert "is_live" not in result


def test_parse_betr_prop_is_live_absent_when_missing():
    raw = _raw_betr_prop()
    raw.pop("is_live", None)
    result = parse_betr_prop(raw)
    assert result is not None
    assert "is_live" not in result
