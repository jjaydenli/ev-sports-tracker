import pytest

from config.pipeline_sources import (
    PIPELINE_LEAGUES,
    dk_league_key,
    normalize_league,
    parse_csv_sources,
    parse_leagues,
)


def test_dk_league_key_maps_mlb():
    assert dk_league_key("MLB") == "mlb"
    assert dk_league_key("NBA") == "nba"
    assert dk_league_key("WNBA") == "wnba"


def test_parse_leagues_subset():
    assert parse_leagues("nba,mlb") == ("NBA", "MLB")
    assert parse_leagues("wnba") == ("WNBA",)


def test_normalize_league_uppercases():
    assert normalize_league("mlb") == "MLB"


def test_parse_csv_sources_defaults_none():
    assert parse_csv_sources(None, valid=("betr",), label="dfs") is None


def test_parse_csv_sources_rejects_unknown():
    with pytest.raises(ValueError, match="unknown books"):
        parse_csv_sources("caesar", valid=("dk", "fd"), label="books")


def test_pipeline_leagues_includes_wnba():
    assert "WNBA" in PIPELINE_LEAGUES
