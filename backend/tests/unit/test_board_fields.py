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

from config.sharp_books import SHARP_BOOK_BY_NAME

BOARD_FIELDS = Path(__file__).resolve().parents[3] / "frontend" / "lib" / "board-fields.json"


def test_every_frontend_board_field_is_an_engine_row_key(s1_ev_rows: list[dict]) -> None:
    fields: dict[str, str] = json.loads(BOARD_FIELDS.read_text(encoding="utf-8"))
    assert fields, "board-fields.json lists no fields"
    (row,) = s1_ev_rows

    missing = {name: key for name, key in fields.items() if key not in row}
    assert not missing, f"frontend fields with no engine row key: {missing}"


FRONTEND = BOARD_FIELDS.parents[1]
BOOKS = FRONTEND / "lib" / "books.json"
# Every book a run's ``sources`` map can name (``<book>:<league>``); the status pill
# names each one through the registry.
PILL_SOURCE_BOOKS = ("betr", "dk", "fd", "espn")


def test_every_registry_book_resolves(s1_ev_rows: list[dict]) -> None:
    """Each ``books.json`` entry's odds names reach an engine row key, its ``sharpName`` is
    a name the engine writes into ``sharp_books``, and its logo is a file.

    Oracle: the S1 engine row, ``SHARP_BOOK_BY_NAME`` and the filesystem, not the registry
    under test. A registry
    walk proving one property, so one loop rather than a parametrize per book. Blind spot:
    an ``under`` pointed at an over key still resolves (the plan's manual check 2).
    """
    fields: dict[str, str] = json.loads(BOARD_FIELDS.read_text(encoding="utf-8"))
    books: list[dict] = json.loads(BOOKS.read_text(encoding="utf-8"))
    (row,) = s1_ev_rows

    problems: list[str] = []
    for book in books:
        for side in ("over", "under"):
            name = book.get(side)
            if name is None:
                continue
            if name not in fields:
                problems.append(f"{book['key']}.{side}: {name!r} is not in board-fields.json")
            elif fields[name] not in row:
                problems.append(f"{book['key']}.{side}: {fields[name]!r} is not an engine row key")
        sharp_name = book.get("sharpName")
        if sharp_name is not None and sharp_name not in SHARP_BOOK_BY_NAME:
            problems.append(f"{book['key']}.sharpName: {sharp_name!r} is not a sharp book")
        logo = book.get("logo")
        if logo is not None and not (FRONTEND / "public" / logo.lstrip("/")).is_file():
            problems.append(f"{book['key']}.logo: {logo!r} is not a file under frontend/public/")
    assert not problems, problems

    missing = set(PILL_SOURCE_BOOKS) - {book["key"] for book in books}
    assert not missing, f"source keys with no registry entry: {sorted(missing)}"
