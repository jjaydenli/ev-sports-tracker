"""ESPN parser gap tests — covers uncovered paths in parsers/espn_parser.py."""

from __future__ import annotations

from parsers.espn_parser import _line_entries, parse_espn_prop, parse_espn_props


# ---------------------------------------------------------------------------
# _line_entries
# ---------------------------------------------------------------------------


def test_line_entries_returns_lines_list_when_present() -> None:
    raw = {"lines": [{"line": 6.5, "over_odds": -110, "under_odds": -110}]}
    entries = _line_entries(raw)
    assert len(entries) == 1
    assert entries[0]["line"] == 6.5


def test_line_entries_falls_back_to_flat_row_when_no_lines_key() -> None:
    raw = {"player": "P", "line": 5.5, "over_odds": -110, "under_odds": -115}
    entries = _line_entries(raw)
    assert entries == [raw]


def test_line_entries_returns_empty_for_row_without_line_or_lines() -> None:
    assert _line_entries({"player": "P", "market": "hits"}) == []


# ---------------------------------------------------------------------------
# parse_espn_prop — valid paths
# ---------------------------------------------------------------------------


def _base_espn() -> dict:
    return {
        "sportsbook": "ESPN",
        "player": "Shohei Ohtani",
        "market": "strikeouts",
        "line": 6.5,
        "over_odds": -115,
        "under_odds": -115,
        "is_main_line": True,
        "league": "MLB",
        "event_start": "2026-07-01T21:00:00.000Z",
    }


def test_parse_espn_prop_returns_normalized_row() -> None:
    prop = parse_espn_prop(_base_espn())
    assert prop is not None
    assert prop["sportsbook"] == "ESPN"
    assert prop["player"] == "Shohei Ohtani"
    assert prop["market"] == "strikeouts"
    assert prop["line"] == 6.5
    assert prop["over_odds"] == -115
    assert prop["under_odds"] == -115
    assert prop["league"] == "MLB"
    assert prop["is_main_line"] is True


def test_parse_espn_prop_league_uppercased() -> None:
    raw = {**_base_espn(), "league": "mlb"}
    prop = parse_espn_prop(raw)
    assert prop is not None
    assert prop["league"] == "MLB"


def test_parse_espn_prop_game_propagated() -> None:
    raw = {**_base_espn(), "game": "LAD@SF"}
    prop = parse_espn_prop(raw)
    assert prop is not None
    assert prop["game"] == "LAD@SF"


# ---------------------------------------------------------------------------
# parse_espn_prop — missing required fields → None
# ---------------------------------------------------------------------------


def test_parse_espn_prop_missing_player_returns_none() -> None:
    raw = {**_base_espn()}
    del raw["player"]
    assert parse_espn_prop(raw) is None


def test_parse_espn_prop_missing_over_odds_returns_none() -> None:
    raw = {**_base_espn()}
    del raw["over_odds"]
    assert parse_espn_prop(raw) is None


def test_parse_espn_prop_missing_under_odds_returns_none() -> None:
    raw = {**_base_espn()}
    del raw["under_odds"]
    assert parse_espn_prop(raw) is None


def test_parse_espn_prop_none_over_odds_returns_none() -> None:
    raw = {**_base_espn(), "over_odds": None}
    assert parse_espn_prop(raw) is None


def test_parse_espn_prop_missing_line_returns_none() -> None:
    raw = {**_base_espn()}
    del raw["line"]
    assert parse_espn_prop(raw) is None


# ---------------------------------------------------------------------------
# parse_espn_props — grouped ladder expansion
# ---------------------------------------------------------------------------


def test_parse_espn_props_expands_grouped_ladder() -> None:
    raw = [
        {
            "sportsbook": "ESPN",
            "player": "Shohei Ohtani",
            "market": "strikeouts",
            "league": "MLB",
            "event_start": "2026-07-01T21:00:00.000Z",
            "lines": [
                {"line": 5.5, "over_odds": -130, "under_odds": 110, "is_main_line": True},
                {"line": 6.5, "over_odds": -115, "under_odds": -115, "is_main_line": False},
            ],
        }
    ]
    props = parse_espn_props(raw)
    assert len(props) == 2
    lines = {p["line"] for p in props}
    assert lines == {5.5, 6.5}
    for prop in props:
        assert prop["league"] == "MLB"
        assert prop["player"] == "Shohei Ohtani"


def test_parse_espn_props_flat_row_format() -> None:
    raw = [
        {
            "sportsbook": "ESPN",
            "player": "Aaron Judge",
            "market": "hits",
            "line": 1.5,
            "over_odds": -140,
            "under_odds": 120,
        }
    ]
    props = parse_espn_props(raw)
    assert len(props) == 1
    assert props[0]["line"] == 1.5


def test_parse_espn_props_skips_rows_with_missing_odds() -> None:
    raw = [
        {"player": "P", "market": "hits", "line": 1.5, "over_odds": -120, "under_odds": -120},
        {"player": "Q", "market": "hits"},  # no line entry
        {"player": "R", "market": "hits", "line": 1.5, "over_odds": None, "under_odds": -120},
    ]
    props = parse_espn_props(raw)
    assert len(props) == 1
    assert props[0]["player"] == "P"


def test_parse_espn_props_empty_input_returns_empty() -> None:
    assert parse_espn_props([]) == []
