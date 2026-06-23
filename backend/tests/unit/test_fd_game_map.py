import json
from pathlib import Path

from config.fd_competitions import FD_LEAGUE_SLATES, build_event_game_map

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "fd_league_mlb_events.json"


def _load_mlb_payload() -> dict:
    return json.loads(FIXTURE.read_text())


def test_build_event_game_map_resolves_full_names_to_canonical_abbrevs():
    payload = _load_mlb_payload()
    mapping = build_event_game_map(
        payload, competition_id=FD_LEAGUE_SLATES["mlb"]["competition_id"]
    )
    # Pitcher annotation stripped; betr-canonical abbreviations (CHW not CWS).
    assert mapping["35730469"] == "CHW@NYY"
    assert mapping["35730465"] == "MIN@TEX"
    assert mapping["35730470"] == "STL@KC"
    # Every resolved game is a canonical AWAY@HOME pair.
    assert all("@" in game for game in mapping.values())


def test_build_event_game_map_skips_non_matchup_events():
    payload = _load_mlb_payload()
    mapping = build_event_game_map(
        payload, competition_id=FD_LEAGUE_SLATES["mlb"]["competition_id"]
    )
    names = {
        v.get("name") for v in (payload["attachments"]["events"]).values()
    }
    assert any("Futures" in (n or "") for n in names)  # futures present in fixture
    # ...but no futures/markets event leaks a game key.
    assert all(" " not in game for game in mapping.values())
