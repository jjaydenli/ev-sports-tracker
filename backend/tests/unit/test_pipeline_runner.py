import json
from unittest.mock import AsyncMock, patch

from core.pipeline_runner import run_refresh


def _write_normalized(tmp_path, betr_count: int, dk_count: int) -> None:
    betr = [
        {
            "sportsbook": "Betr",
            "player": f"Player {index}",
            "market": "points",
            "line": 10.5 + index,
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
            "over_odds": -110,
            "under_odds": -110,
        }
        for index in range(dk_count)
    ]
    (tmp_path / "betr_normalized.json").write_text(json.dumps(betr), encoding="utf-8")
    (tmp_path / "dk_normalized.json").write_text(json.dumps(dk), encoding="utf-8")


@patch("core.pipeline_runner._preflight_betr_auth")
def test_run_refresh_skip_scrape_writes_ev(mock_preflight, tmp_path):
    _write_normalized(tmp_path, betr_count=2, dk_count=2)

    code = run_refresh(data_dir=tmp_path, skip_scrape=True)

    assert code == 0
    mock_preflight.assert_not_called()
    assert (tmp_path / "match_report.json").exists()
    assert (tmp_path / "unmatched_betr.json").exists()
    assert (tmp_path / "unmatched_dk.json").exists()
    output = tmp_path / "ev_opportunities.json"
    assert output.exists()
    opportunities = json.loads(output.read_text(encoding="utf-8"))
    assert isinstance(opportunities, list)
    if opportunities:
        assert "plus_ev" in opportunities[0]
        assert len(opportunities) <= 15


@patch("core.pipeline_runner._scrape_betr", new_callable=AsyncMock)
@patch("core.pipeline_runner._preflight_betr_auth")
def test_run_refresh_betr_only_skips_ev(mock_preflight, mock_scrape_betr, tmp_path):
    mock_scrape_betr.return_value = 10

    with patch("core.pipeline_runner.normalize_all") as mock_normalize:
        code = run_refresh(data_dir=tmp_path, betr_only=True)

    assert code == 0
    mock_preflight.assert_called_once()
    mock_normalize.assert_called_once_with(tmp_path)
