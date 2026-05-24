from archive.dabble.dabble_parser import parse_dabble_prop


def test_parse_dabble_prop_canonicalizes_market():
    raw_prop = {
        "sportsbook": "Dabble",
        "player": "Test Player",
        "market": "points_rebounds",
        "line": 25.5,
        "prop_type": "standard",
        "over_odds": -122,
        "under_odds": -122,
    }

    result = parse_dabble_prop(raw_prop)

    assert result is not None
    assert result["market"] == "pts+reb"
