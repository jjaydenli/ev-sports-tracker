from config.pipeline_sources import BOOK_SOURCES, BOOK_TO_PLATFORM, SOURCE_TO_PLATFORM


def test_espn_registered_in_book_sources():
    assert "espn" in BOOK_SOURCES


def test_espn_platform_mapping():
    assert BOOK_TO_PLATFORM["espn"] == "espn"
    assert SOURCE_TO_PLATFORM["espn"] == "espn"
