"""Tests for DK prop subcategory discovery config helpers."""

import pytest

from config.dk_discovery import parse_id_ranges


def test_parse_id_ranges_single():
    assert parse_id_ranges(["6580-6760"]) == ((6580, 6760),)


def test_parse_id_ranges_multiple():
    assert parse_id_ranges(["100-102", "200-201"]) == ((100, 102), (200, 201))


def test_parse_id_ranges_rejects_inverted():
    with pytest.raises(ValueError, match="start > end"):
        parse_id_ranges(["7000-6400"])
