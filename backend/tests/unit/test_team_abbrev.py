from config.team_abbrev import (
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
