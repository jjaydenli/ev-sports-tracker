"""Tests for DK prop subcategory discovery config helpers."""

import pytest

from config.dk_discovery import discovery_id_ranges, parse_id_ranges


def test_parse_id_ranges_single():
    assert parse_id_ranges(["6580-6760"]) == ((6580, 6760),)


def test_parse_id_ranges_multiple():
    assert parse_id_ranges(["100-102", "200-201"]) == ((100, 102), (200, 201))


def test_parse_id_ranges_rejects_inverted():
    with pytest.raises(ValueError, match="start > end"):
        parse_id_ranges(["7000-6400"])


def test_discovery_id_ranges_mlb_live_includes_high_band():
    ranges = discovery_id_ranges("mlb", live=True)
    assert (9000, 10100) in ranges
    assert (17000, 17600) in ranges


def test_discovery_id_ranges_mlb_pregame_excludes_live_only_band():
    ranges = discovery_id_ranges("mlb", live=False)
    assert (9000, 10100) not in ranges
