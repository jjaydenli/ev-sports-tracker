from config.pipeline_sources import PIPELINE_LEAGUES
from config.team_abbrev import (
    CODE_ONLY_LEAGUES,
    TEAMS_BY_LEAGUE,
    _normalize_name,
    abbr_from_full_name,
    canonicalize_team_abbr,
    game_key_from_full_names,
)


def test_canonicalize_known_deviations():
    assert canonicalize_team_abbr("CWS") == "CHW"
    assert canonicalize_team_abbr("PHO") == "PHX"
    assert canonicalize_team_abbr("WAS") == "WSH"


def test_canonicalize_passes_through_canonical_and_lowercase():
    assert canonicalize_team_abbr("CHW") == "CHW"
    assert canonicalize_team_abbr("nyy") == "NYY"
    assert canonicalize_team_abbr(" tb ") == "TB"


def test_abbr_from_full_name_strips_pitcher_annotation():
    assert abbr_from_full_name("Minnesota Twins (J Ryan)") == "MIN"
    assert abbr_from_full_name("Texas Rangers (J Leiter)") == "TEX"


def test_abbr_from_full_name_punctuation_insensitive():
    assert abbr_from_full_name("St. Louis Cardinals") == "STL"
    assert abbr_from_full_name("st louis cardinals") == "STL"


def test_abbr_from_full_name_unmapped_returns_none():
    assert abbr_from_full_name("Some Fake Team") is None


def test_game_key_from_full_names_canonical():
    assert (
        game_key_from_full_names(
            "Cleveland Guardians (S Bibee)", "Chicago White Sox (D Martin)"
        )
        == "CLE@CHW"
    )
    assert (
        game_key_from_full_names("Philadelphia Phillies", "Washington Nationals")
        == "PHI@WSH"
    )


def test_game_key_from_full_names_unmapped_returns_none():
    assert game_key_from_full_names("Philadelphia Phillies", "Some Fake Team") is None


def test_full_names_are_unique_across_leagues():
    """The league-blind map merges every league; a repeated name would keep one code."""
    seen: dict[str, str] = {}
    repeated = []
    for league, teams in TEAMS_BY_LEAGUE.items():
        for name in teams:
            key = _normalize_name(name)
            if key in seen:
                repeated.append(f"{name!r} in {seen[key]} and {league}")
            seen[key] = league
    assert not repeated, repeated


def test_every_pipeline_league_is_named_or_code_only():
    """The board's team search reads names per league; a league in neither table would
    match codes only with no record that it was meant to."""
    unnamed = [lg for lg in PIPELINE_LEAGUES if lg not in TEAMS_BY_LEAGUE]
    assert sorted(unnamed) == sorted(CODE_ONLY_LEAGUES), (
        f"named nowhere: {sorted(set(unnamed) - set(CODE_ONLY_LEAGUES))}; "
        f"code-only but named: {sorted(set(CODE_ONLY_LEAGUES) - set(unnamed))}"
    )
