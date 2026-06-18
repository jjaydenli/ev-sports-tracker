import json
from unittest.mock import AsyncMock, patch

from config.pipeline_sources import PIPELINE_LEAGUES
from core.ev_pipeline import BETR_NORMALIZED, DK_NORMALIZED
from core.pipeline_artifacts import load_wrapped_board, save_wrapped_board
from core.pipeline_runner import build_parser, merge_leagues_from_args, normalize_league_flag_argv
from core.scrape_result import ScrapeResult


def _write_wrapped_normalized(tmp_path, betr_count: int, dk_count: int, *, run_id: str = "test-run") -> None:
    betr = [
        {
            "sportsbook": "Betr",
            "player": f"Player {index}",
            "market": "points",
            "line": 10.5 + index,
            "league": "NBA",
            "over_odds": -120,
            "under_odds": -120,
        }
        for index in range(betr_count)
    ]
    dk = [
        {
            "sportsbook": "DraftKings",
            "player": f"Player {index}",
            "market": "points",
            "line": 10.5 + index,
            "league": "NBA",
            "over_odds": -110,
            "under_odds": -110,
        }
        for index in range(dk_count)
    ]
    save_wrapped_board(tmp_path / BETR_NORMALIZED, run_id=run_id, props=betr)
    save_wrapped_board(tmp_path / DK_NORMALIZED, run_id=run_id, props=dk)


def _ok_result(source: str, league: str, count: int) -> ScrapeResult:
    if source == "dk":
        props = [
            {
                "sportsbook": "DraftKings",
                "player": f"DK Player {index}",
                "market": "hits" if league == "MLB" else "points",
                "line": 1.5 + index if league == "MLB" else 10.5 + index,
                "league": league,
                "over_odds": -110,
                "under_odds": -110,
            }
            for index in range(count)
        ]
    else:
        betr_key = "HITS" if league == "MLB" else "POINTS"
        betr_value = 1.5 if league == "MLB" else 10.5
        props = [
            {
                "player": f"Betr Player {index}",
                "key": betr_key,
                "type": "REGULAR",
                "value": betr_value + index,
                "market_id": f"betr-{league}-{index}",
                "league": league,
                "allowed_options": [
                    {"market_option_id": "1", "outcome": "OVER"},
                    {"market_option_id": "2", "outcome": "UNDER"},
                ],
            }
            for index in range(count)
        ]
    return ScrapeResult(
        source=source,
        league=league,
        status="ok",
        prop_count=count,
        props=props,
    )


def _no_events(source: str, league: str) -> ScrapeResult:
    return ScrapeResult(source=source, league=league, status="no_events")


def _skipped(source: str, league: str) -> ScrapeResult:
    return ScrapeResult(
        source=source,
        league=league,
        status="skipped",
        reason="not_configured",
    )


def _basketball_league(league: str) -> bool:
    return league in {"NBA", "WNBA"}


def test_build_parser_has_shorthand_flag_per_pipeline_league():
    parser = build_parser()
    for league in PIPELINE_LEAGUES:
        assert f"--{league.lower()}" in parser.format_usage()


def test_merge_leagues_from_args_wnba_only():
    args = build_parser().parse_args(["--wnba"])
    assert merge_leagues_from_args(args) == ("WNBA",)


def test_merge_leagues_from_args_union_with_leagues():
    args = build_parser().parse_args(["--leagues", "mlb", "--wnba"])
    assert merge_leagues_from_args(args) == ("MLB", "WNBA")


def test_merge_leagues_from_args_none_when_no_league_flags():
    args = build_parser().parse_args([])
    assert merge_leagues_from_args(args) is None


def test_normalize_league_flag_argv_case_insensitive():
    assert normalize_league_flag_argv(["--WNBA"]) == ["--wnba"]
    assert normalize_league_flag_argv(["--NBA", "--MLB"]) == ["--nba", "--mlb"]


@patch("core.pipeline_runner._preflight_betr_auth")
def test_run_refresh_skip_scrape_writes_ev(mock_preflight, tmp_path):
    _write_wrapped_normalized(tmp_path, betr_count=2, dk_count=2)

    from core.pipeline_runner import run_refresh

    code = run_refresh(data_dir=tmp_path, skip_scrape=True)

    assert code == 0
    mock_preflight.assert_not_called()
    assert (tmp_path / "match_report.json").exists()
    output = tmp_path / "ev_opportunities.json"
    assert output.exists()
    _, opportunities = load_wrapped_board(output)
    assert isinstance(opportunities, list)
    if opportunities:
        assert "plus_ev" in opportunities[0]


@patch("core.pipeline_runner.scrape_source_league", new_callable=AsyncMock)
@patch("core.pipeline_runner._preflight_betr_auth")
def test_run_refresh_full_scrape_all_leagues(mock_preflight, mock_scrape, tmp_path):
    async def fake_scrape(source: str, league: str) -> ScrapeResult:
        if source == "fd" and league == "MLB":
            return _skipped("fd", league)
        if _basketball_league(league) and source in {"betr", "dk", "fd"}:
            return _ok_result(source, league, 2)
        return _no_events(source, league)

    mock_scrape.side_effect = fake_scrape

    from core.pipeline_runner import run_refresh

    code = run_refresh(data_dir=tmp_path)

    assert code == 0
    assert mock_scrape.await_count == 9
    _, betr = load_wrapped_board(tmp_path / BETR_NORMALIZED)
    assert len(betr) == 4
    coverage = json.loads((tmp_path / "scrape_coverage.json").read_text(encoding="utf-8"))
    assert coverage["leagues"] == ["NBA", "MLB", "WNBA"]
    assert coverage["sources"]["fd:MLB"]["status"] == "skipped"


@patch("core.pipeline_runner.scrape_source_league", new_callable=AsyncMock)
@patch("core.pipeline_runner._preflight_betr_auth")
def test_run_refresh_scrape_only(mock_preflight, mock_scrape, tmp_path):
    mock_scrape.return_value = _ok_result("betr", "NBA", 1)

    from core.pipeline_runner import run_refresh

    code = run_refresh(data_dir=tmp_path, scrape_only=True, dfs=("betr",), books=())

    assert code == 0
    assert not (tmp_path / "ev_opportunities.json").exists()


@patch("core.pipeline_runner.scrape_source_league", new_callable=AsyncMock)
@patch("core.pipeline_runner._preflight_betr_auth")
def test_run_refresh_partial_books_still_scrapes_all_dfs(mock_preflight, mock_scrape, tmp_path):
    async def fake_scrape(source: str, league: str) -> ScrapeResult:
        if source == "betr":
            return _ok_result("betr", league, 1)
        if source == "dk":
            return _ok_result("dk", league, 1)
        return _skipped("fd", league)

    mock_scrape.side_effect = fake_scrape

    from core.pipeline_runner import run_refresh

    code = run_refresh(data_dir=tmp_path, books=("dk",), leagues=("NBA",))

    assert code == 0
    scraped_sources = {call.args[0] for call in mock_scrape.await_args_list}
    assert scraped_sources == {"betr", "dk"}


@patch("core.pipeline_runner.scrape_source_league", new_callable=AsyncMock)
@patch("core.pipeline_runner._preflight_betr_auth")
def test_run_refresh_fails_without_dfs_and_book(mock_preflight, mock_scrape, tmp_path):
    mock_scrape.return_value = _no_events("betr", "NBA")

    from core.pipeline_runner import run_refresh

    code = run_refresh(data_dir=tmp_path, leagues=("NBA",))

    assert code == 1


@patch("core.pipeline_runner.scrape_source_league", new_callable=AsyncMock)
@patch("core.pipeline_runner._preflight_betr_auth")
def test_run_refresh_continues_when_one_league_empty(mock_preflight, mock_scrape, tmp_path):
    async def fake_scrape(source: str, league: str) -> ScrapeResult:
        if league == "NBA":
            return _no_events(source, league)
        if league == "MLB" and source in {"betr", "dk"}:
            return _ok_result(source, league, 2)
        if league == "MLB" and source == "fd":
            return _skipped("fd", league)
        return _no_events(source, league)

    mock_scrape.side_effect = fake_scrape

    from core.pipeline_runner import run_refresh

    code = run_refresh(data_dir=tmp_path)

    assert code == 0
    _, betr = load_wrapped_board(tmp_path / BETR_NORMALIZED)
    assert len(betr) == 2
