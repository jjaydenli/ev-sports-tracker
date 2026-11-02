import argparse
import json
from pathlib import Path

import httpx
import pytest

from config.dk_subcategories import DK_NBA_LIVE_STAT_CATEGORIES
from scrapers.sportsbooks import dk_api, fd_api
from scrapers.sportsbooks.dk_api import classify_tab_shape
from scripts import discover_prop_tabs as discover
from scripts.discover_prop_tabs import (
    TabProbe,
    neighborhood_ids,
    parse_id_spec,
    summarize,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
HIT = {"markets": 3}


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest.mark.parametrize(
    ("fixture", "shape"),
    [
        ("dk_markets_steals_ou_34183767.json", "ou"),
        ("dk_markets_steals_milestone_34183767.json", "milestone"),
        ("dk_markets_double_double_live_34930762.json", "yes_only"),
    ],
)
def test_classify_tab_shape_on_captured_tabs(fixture, shape):
    assert classify_tab_shape(_fixture(fixture)) == shape


def test_parse_id_spec_expands_ranges_and_dedupes_in_order():
    assert parse_id_spec(["100-102", "7", "101"]) == ["100", "101", "102", "7"]


def test_parse_id_spec_rejects_descending_range():
    with pytest.raises(ValueError, match="descending"):
        parse_id_spec(["102-100"])


def test_neighborhood_ids_merges_overlap_and_stays_positive():
    assert neighborhood_ids(["2", "4"], 1) == ["1", "2", "3", "4", "5"]
    assert neighborhood_ids(["1"], 2) == ["1", "2", "3"]


def test_summarize_tab_empty_on_every_valid_event_is_absent():
    result = summarize(
        [
            TabProbe("e1", "1", is_control=True, **HIT),
            TabProbe("e1", "2"),
            TabProbe("e2", "1", is_control=True, **HIT),
            TabProbe("e2", "2"),
        ]
    )
    assert result.absent == ["2"]
    assert result.valid_events == ["e1", "e2"]


def test_summarize_tab_on_one_of_two_events_is_a_hit_not_absent():
    result = summarize(
        [
            TabProbe("e1", "1", is_control=True, **HIT),
            TabProbe("e1", "2"),
            TabProbe("e2", "1", is_control=True, **HIT),
            TabProbe("e2", "2", **HIT),
        ]
    )
    assert result.absent == []
    assert [probe.event_id for probe in result.hits["2"]] == ["e2"]


def test_summarize_blocked_tab_is_unknown_not_absent():
    result = summarize(
        [TabProbe("e1", "1", is_control=True, **HIT), TabProbe("e1", "2", blocked=True)]
    )
    assert result.absent == []
    assert result.blocked == 1


def test_summarize_event_with_empty_control_gives_no_verdict():
    result = summarize([TabProbe("e1", "1", is_control=True), TabProbe("e1", "2")])
    assert result.valid_events == []
    assert result.unposted_events == ["e1"]
    assert result.absent == []


def test_summarize_keeps_a_hit_from_an_event_with_an_empty_control():
    result = summarize([TabProbe("e1", "1", is_control=True), TabProbe("e1", "2", **HIT)])
    assert result.valid_events == []
    assert [probe.event_id for probe in result.hits["2"]] == ["e1"]


def test_summarize_unposted_event_does_not_count_against_a_tab():
    result = summarize(
        [
            TabProbe("e1", "1", is_control=True, **HIT),
            TabProbe("e1", "2", **HIT),
            TabProbe("e2", "1", is_control=True),
            TabProbe("e2", "2"),
        ]
    )
    assert result.valid_events == ["e1"]
    assert "2" in result.hits
    assert result.absent == []


def _args(**overrides) -> argparse.Namespace:
    defaults = {
        "league": "nba",
        "state": "live",
        "event_id": ["e1"],
        "events": 2,
        "ids": None,
        "pad": 1,
        "concurrency": 2,
    }
    return argparse.Namespace(**{**defaults, **overrides})


def _patch_client(monkeypatch, handler) -> None:
    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def client(**kwargs):
        return real_client(transport=transport, **kwargs)

    monkeypatch.setattr(discover.httpx, "AsyncClient", client)


@pytest.mark.asyncio
async def test_discover_dk_control_hit_and_blocked_tab_end_to_end(monkeypatch):
    control = DK_NBA_LIVE_STAT_CATEGORIES["points"]
    yes_only = _fixture("dk_markets_double_double_live_34930762.json")
    monkeypatch.setattr(dk_api, "DK_MARKETS_RETRY_DELAYS_SEC", (0, 0, 0, 0))

    def handler(request: httpx.Request) -> httpx.Response:
        vars_ = request.url.params["templateVars"]
        tab = vars_.split(",")[1]
        if tab == control:
            return httpx.Response(200, json=_fixture("dk_markets_points_34183767.json"))
        if tab == "19084":
            return httpx.Response(200, json=yes_only)
        if tab == "19083":
            return httpx.Response(403)
        return httpx.Response(200, json={"markets": [], "selections": []})

    _patch_client(monkeypatch, handler)
    probes = await discover.discover_dk(_args(ids=["19083-19085"]))
    result = summarize(probes)

    assert result.valid_events == ["e1"]
    assert result.hits["19084"][0].shape == "yes_only"
    assert result.blocked == 1
    assert result.absent == ["19085"]


@pytest.mark.asyncio
async def test_discover_fd_lists_tabs_and_uses_known_tab_as_control(monkeypatch):
    payload = _fixture("fd_event_35639109_player_points.json")

    async def fake_page(_client, _event_id):
        return payload

    monkeypatch.setattr(fd_api, "fetch_event_page", fake_page)
    result = summarize(await discover.discover_fd(_args(event_id=["35639109"])))

    assert result.valid_events == ["35639109"]
    assert list(result.hits) == ["Player Points"]
