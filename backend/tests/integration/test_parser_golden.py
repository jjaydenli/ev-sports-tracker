"""Parser round-trip golden snapshots.

For each book, runs the scraper→normalize chain on existing fixtures and
snapshots the sorted normalized output.  Upstream API shape drift that changes
parser output fails these tests.

Re-bless with:  pytest --snapshot-update tests/integration/test_parser_golden.py
"""

from __future__ import annotations

import json
from pathlib import Path

from syrupy.assertion import SnapshotAssertion

from parsers.betr_parser import parse_betr_props
from parsers.dk_parser import parse_dk_props
from parsers.espn_parser import parse_espn_props
from parsers.fd_parser import parse_fd_props
from scrapers.dfs.betr.betr_engine import extract_raw_props
from scrapers.sportsbooks.dk_api import flatten_markets_response
from scrapers.sportsbooks.espn_api import flatten_drawer_content
from scrapers.sportsbooks.fd_api import flatten_event_page_response

_FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"
_ESPN_EVENT_ID = "105477089"
_DK_MLB_EVENT_ID = "34267452"
_FD_PITCHER_EVENT_ID = "35730475"
_FD_MILESTONES_EVENT_ID = "35733870"


def _load(name: str) -> dict:
    return json.loads((_FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _clean_prop(prop: dict) -> dict:
    """Snapshot-safe prop: round floats, keep required fields only."""
    return {
        "sportsbook": prop.get("sportsbook"),
        "player": prop.get("player"),
        "market": prop.get("market"),
        "line": round(float(prop.get("line", 0)), 2),
        "over_odds": prop.get("over_odds"),
        "under_odds": prop.get("under_odds"),
        "line_kind": prop.get("line_kind"),
        "is_main_line": prop.get("is_main_line"),
        "league": prop.get("league"),
    }


def _sort_key(prop: dict) -> tuple:
    return (prop.get("player") or "", prop.get("market") or "", prop.get("line") or 0.0)


# ---------------------------------------------------------------------------
# DK parser — hits fixture (18 rows)
# ---------------------------------------------------------------------------


def test_dk_parser_hits_fixture_golden(snapshot: SnapshotAssertion) -> None:
    """DK mlb hits parse round-trip: every row shape matches snapshot."""
    payload = _load("dk_markets_mlb_hits.json")
    raw = flatten_markets_response(
        payload,
        event_id=_DK_MLB_EVENT_ID,
        market="hits",
        prop_subcategory_id="1000",
    )
    props = sorted([_clean_prop(p) for p in parse_dk_props(raw)], key=_sort_key)
    assert props == snapshot
    assert len(props) > 0


def test_dk_parser_strikeouts_fixture_golden(snapshot: SnapshotAssertion) -> None:
    """DK mlb strikeouts parse round-trip."""
    payload = _load("dk_markets_mlb_strikeouts.json")
    raw = flatten_markets_response(
        payload,
        event_id=_DK_MLB_EVENT_ID,
        market="strikeouts",
        prop_subcategory_id="1001",
    )
    props = sorted([_clean_prop(p) for p in parse_dk_props(raw)], key=_sort_key)
    assert props == snapshot
    assert len(props) > 0


# ---------------------------------------------------------------------------
# FanDuel parser — pitcher props fixture
# ---------------------------------------------------------------------------


def test_fd_parser_pitcher_strikeouts_golden(snapshot: SnapshotAssertion) -> None:
    """FD pitcher strikeouts parse round-trip."""
    payload = _load("fd_event_35730475_pitcher_props.json")
    raw = flatten_event_page_response(
        payload,
        event_id=_FD_PITCHER_EVENT_ID,
        tab="pitcher-props",
        markets={"strikeouts"},
        league="mlb",
    )
    props = sorted([_clean_prop(p) for p in parse_fd_props(raw)], key=_sort_key)
    assert props == snapshot
    assert len(props) > 0


# ---------------------------------------------------------------------------
# ESPN parser — batter hits and pitcher strikeouts drawer fixtures
# ---------------------------------------------------------------------------


def test_espn_parser_batter_hits_golden(snapshot: SnapshotAssertion) -> None:
    """ESPN batter hits drawer parse round-trip."""
    fixture = _load("espn_drawer_batter_hits.json")
    raw = flatten_drawer_content(fixture, event_id=_ESPN_EVENT_ID, league="mlb")
    props = sorted([_clean_prop(p) for p in parse_espn_props(raw)], key=_sort_key)
    assert props == snapshot
    assert len(props) > 0


def test_espn_parser_pitcher_strikeouts_golden(snapshot: SnapshotAssertion) -> None:
    """ESPN pitcher strikeouts drawer parse round-trip."""
    fixture = _load("espn_drawer_pitcher_strikeouts.json")
    raw = flatten_drawer_content(fixture, event_id=_ESPN_EVENT_ID, league="mlb")
    props = sorted([_clean_prop(p) for p in parse_espn_props(raw)], key=_sort_key)
    assert props == snapshot
    assert len(props) > 0


# ---------------------------------------------------------------------------
# Betr parser — pregame MLB fixture (large; snapshot first 10 sorted rows)
# ---------------------------------------------------------------------------


def test_betr_parser_mlb_pregame_golden(snapshot: SnapshotAssertion) -> None:
    """Betr MLB pregame parse round-trip — first 10 props sorted by player."""
    fixture = _load("betr_mlb_pregame.json")
    raw = extract_raw_props(fixture, league="MLB")
    all_props = sorted([_clean_prop(p) for p in parse_betr_props(raw)], key=_sort_key)
    # Snapshot first 10 to keep file size reasonable; count guards total regression.
    assert len(all_props) >= 10, f"expected ≥10 Betr pregame props, got {len(all_props)}"
    assert all_props[:10] == snapshot


def test_betr_parser_mlb_pregame_count(snapshot: SnapshotAssertion) -> None:
    """Snapshot Betr MLB pregame prop count — catches parser filtering regressions."""
    fixture = _load("betr_mlb_pregame.json")
    raw = extract_raw_props(fixture, league="MLB")
    props = parse_betr_props(raw)
    assert {"total": len(props)} == snapshot
