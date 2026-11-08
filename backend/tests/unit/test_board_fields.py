"""The live board page reads only row keys the engine emits.

``frontend/lib/board-fields.json`` maps each field the page renders to its engine row
key. The page renders a missing key as a dash, so a renamed engine key would blank a
column with no error; this guard turns that drift into a failing test.

Oracle: a real row from ``find_ev_opportunities`` over the S1 scenario (the
``s1_ev_rows`` fixture), not the frontend list under test. Presence only: FD keys are
``None`` in S1, which is still a key the engine emits.
"""

from __future__ import annotations

import json
from pathlib import Path

BOARD_FIELDS = Path(__file__).resolve().parents[3] / "frontend" / "lib" / "board-fields.json"


def test_every_frontend_board_field_is_an_engine_row_key(s1_ev_rows: list[dict]) -> None:
    fields: dict[str, str] = json.loads(BOARD_FIELDS.read_text(encoding="utf-8"))
    assert fields, "board-fields.json lists no fields"
    (row,) = s1_ev_rows

    missing = {name: key for name, key in fields.items() if key not in row}
    assert not missing, f"frontend fields with no engine row key: {missing}"
