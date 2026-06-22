import json
from unittest.mock import AsyncMock, patch

from config.pipeline_sources import PIPELINE_LEAGUES
from core.ev_pipeline import BETR_NORMALIZED, DK_NORMALIZED, FD_NORMALIZED, load_comparison_inputs
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
    elif source == "fd":
        props = [
            {
                "sportsbook": "FanDuel",
                "player": f"FD Player {index}",
                "market": "hits" if league == "MLB" else "points",
                "line": 1.5 + index if league == "MLB" else 10.5 + index,
                "league": league,
                "over_odds": -115,
                "under_odds": -105,
            }
            for index in range(count)
        ]
    elif source == "espn":
        props = [
            {
                "sportsbook": "ESPN",
                "player": f"ESPN Player {index}",
                "market": "hits" if league == "MLB" else "points",
                "line": 1.5 + index if league == "MLB" else 10.5 + index,
                "league": league,
                "over_odds": -118,
                "under_odds": -102,
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
        if _basketball_league(league) and source in {"betr", "dk", "fd", "espn"}:
            return _ok_result(source, league, 2)
        if league == "MLB" and source in {"betr", "dk", "fd", "espn"}:
            return _ok_result(source, league, 2)
        return _no_events(source, league)

    mock_scrape.side_effect = fake_scrape

    from core.pipeline_runner import run_refresh

    code = run_refresh(data_dir=tmp_path)

    assert code == 0
    assert mock_scrape.await_count == 12
    _, betr = load_wrapped_board(tmp_path / BETR_NORMALIZED)
    assert len(betr) == 6
    coverage = json.loads((tmp_path / "scrape_coverage.json").read_text(encoding="utf-8"))
    assert coverage["leagues"] == ["NBA", "MLB", "WNBA"]
    assert coverage["sources"]["fd:MLB"]["status"] == "ok"


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


def _write_stale_dk_board(tmp_path, *, run_id: str = "stale-run") -> None:
    dk = [
        {
            "sportsbook": "DraftKings",
            "player": "Stale Player",
            "market": "hits",
            "line": 1.5,
            "league": "MLB",
            "over_odds": -110,
            "under_odds": -110,
        }
    ]
    save_wrapped_board(tmp_path / DK_NORMALIZED, run_id=run_id, props=dk)


def _fd_ok_result(league: str, count: int) -> ScrapeResult:
    props = [
        {
            "sportsbook": "FanDuel",
            "player": f"FD Player {index}",
            "market": "hits",
            "line": 1.5 + index,
            "league": league,
            "over_odds": -115,
            "under_odds": -105,
        }
        for index in range(count)
    ]
    return ScrapeResult(
        source="fd",
        league=league,
        status="ok",
        prop_count=count,
        props=props,
    )


@patch("core.pipeline_runner.scrape_source_league", new_callable=AsyncMock)
@patch("core.pipeline_runner._preflight_betr_auth")
def test_run_refresh_espn_only_partial_run(mock_preflight, mock_scrape, tmp_path):
    _write_stale_dk_board(tmp_path)

    async def fake_scrape(source: str, league: str) -> ScrapeResult:
        if source == "betr" and league == "MLB":
            return _ok_result("betr", league, 2)
        if source == "espn" and league == "MLB":
            return _ok_result("espn", league, 1)
        return _no_events(source, league)

    mock_scrape.side_effect = fake_scrape

    from core.pipeline_runner import run_refresh

    code = run_refresh(data_dir=tmp_path, books=("espn",), leagues=("MLB",))

    assert code == 0
    betr_props, dk_props, fd_props, espn_props = load_comparison_inputs(
        tmp_path,
        expected_run_id=json.loads(
            (tmp_path / "scrape_coverage.json").read_text(encoding="utf-8")
        )["run_id"],
        active_sources=("betr", "espn"),
    )
    assert betr_props
    assert dk_props == []
    assert fd_props == []
    assert espn_props


@patch("core.pipeline_runner.scrape_source_league", new_callable=AsyncMock)
@patch("core.pipeline_runner._preflight_betr_auth")
def test_run_refresh_fd_only_ignores_stale_dk_board(mock_preflight, mock_scrape, tmp_path):
    _write_stale_dk_board(tmp_path)

    async def fake_scrape(source: str, league: str) -> ScrapeResult:
        if source == "betr" and league == "MLB":
            return _ok_result("betr", league, 2)
        if source == "fd" and league == "MLB":
            return _fd_ok_result(league, 1)
        return _no_events(source, league)

    mock_scrape.side_effect = fake_scrape

    from core.pipeline_runner import run_refresh

    code = run_refresh(data_dir=tmp_path, books=("fd",), leagues=("MLB",))

    assert code == 0
    assert (tmp_path / "ev_opportunities.json").exists()
    _, stale_dk = load_wrapped_board(tmp_path / DK_NORMALIZED)
    assert len(stale_dk) == 1
    betr_props, dk_props, fd_props, _espn_props = load_comparison_inputs(
        tmp_path,
        expected_run_id=json.loads(
            (tmp_path / "scrape_coverage.json").read_text(encoding="utf-8")
        )["run_id"],
        active_sources=("betr", "fd"),
    )
    assert betr_props
    assert dk_props == []
    assert fd_props


def test_load_comparison_inputs_skips_inactive_sources_with_stale_run_id(tmp_path):
    current_run = "current-run"
    betr = [
        {
            "sportsbook": "Betr",
            "player": "Player A",
            "market": "hits",
            "line": 1.5,
            "league": "MLB",
            "over_odds": -120,
            "under_odds": -120,
        }
    ]
    fd = [
        {
            "sportsbook": "FanDuel",
            "player": "Player A",
            "market": "hits",
            "line": 1.5,
            "league": "MLB",
            "over_odds": -115,
            "under_odds": -105,
        }
    ]
    save_wrapped_board(tmp_path / BETR_NORMALIZED, run_id=current_run, props=betr)
    save_wrapped_board(tmp_path / FD_NORMALIZED, run_id=current_run, props=fd)
    _write_stale_dk_board(tmp_path)

    betr_props, dk_props, fd_props, _espn_props = load_comparison_inputs(
        tmp_path,
        expected_run_id=current_run,
        active_sources=("betr", "fd"),
    )

    assert len(betr_props) == 1
    assert dk_props == []
    assert len(fd_props) == 1


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
        if league == "MLB" and source in {"betr", "dk", "fd", "espn"}:
            return _ok_result(source, league, 2)
        return _no_events(source, league)

    mock_scrape.side_effect = fake_scrape

    from core.pipeline_runner import run_refresh

    code = run_refresh(data_dir=tmp_path)

    assert code == 0
    _, betr = load_wrapped_board(tmp_path / BETR_NORMALIZED)
    assert len(betr) == 2
