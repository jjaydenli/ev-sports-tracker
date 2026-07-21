# Lint + type-check gate in CI

## Context

The test suite ran in CI, but nothing checked code style or type correctness before merge.
Neither `ruff` nor `mypy` was in `requirements.txt`, and `backend/` had no shared tool
configuration: pytest settings lived in a standalone `pytest.ini`.

## Design decisions

1. **One `pyproject.toml`, not a second config file.** `[tool.ruff]`, `[tool.mypy]`, and
   `[tool.pytest.ini_options]` all live in `backend/pyproject.toml`; `pytest.ini` is deleted
   rather than kept alongside it. pytest resolves config by precedence and never merges the
   two, so leaving both in place would make `pytest.ini` silently win, and any future setting
   added to `pyproject.toml` would be dead. Verified the migration is behavior-neutral: full
   coverage output (including the per-file missing-line report) is unchanged before and after.

2. **`requires-python = ">=3.13"` declared explicitly**, with `mypy` targeting `python_version
   = "3.13"` to match. Without it, `ruff` defaults to inferring an older target version, which
   silently skips modernization rules the newer interpreter supports.

3. **`mypy` excludes `tests/`; `ruff` does not.** Fixture- and mock-heavy test code produces a
   disproportionate share of `mypy` noise for little signal, while `ruff`'s import-hygiene and
   dead-code rules are worth enforcing there too. The exclude is directory-based (`^tests/`)
   rather than a hand-maintained package list, so it can't silently drop a new source directory
   from coverage the way a maintained list would.

4. **`config/__init__.py` gets an explicit `__all__`.** Its re-exports are deliberate, but
   `ruff` has no way to know that without either an `__all__` declaration or a rule-level
   ignore; `__all__` was chosen because a blanket ignore would also hide a genuinely unused
   import in the same file later.

5. **Findings are fixed in code, not suppressed.** No blanket `ignore_errors`, no per-module
   opt-outs. A `# type: ignore[code]` is acceptable only with a reason comment, and only where
   the alternative is a larger refactor out of scope here.

6. **Lint only, no auto-formatter.** The repo carries a large existing line-length debt that a
   formatter would rewrite wholesale, burying the actual gate behind an unrelated reformat.

7. **Workflow hardening bundled in:** explicit read-only `permissions`, a concurrency group that
   cancels superseded runs, a `timeout-minutes` cap (the platform default on a hung job is
   several hours), and dependency caching. Small additions, same job.

8. **Lint and type-check run as steps in the existing test job, after the test step**, not as
   separate jobs, so a lint failure doesn't cost the test result and CI stays a single required
   check.

## Bugs the type check caught

Turning the gate on surfaced two real issues, beyond style:

- A tuple-unpack in the refresh pipeline had its two return values reversed, so the full list
  of scraped props was being written into a coverage file's run-id field instead of the run id
  itself.
- A worker loop zipped two lists that are expected to always stay the same length by
  construction; `zip(..., strict=True)` makes a future violation of that assumption fail loudly
  instead of silently misaligning results.

Several other call sites needed a defensive `isinstance` check before iterating over the result
of a concurrent fetch, since a non-list, non-exception result is a shape the type checker can
prove is otherwise unhandled.

## Non-goals

- No CI Python version matrix. The branch protection rule targets a single required check name,
  and a matrix would rename it out from under that rule.
- No dependency security scanning (`pip-audit`, CodeQL, Dependabot). Each is a real addition
  with its own scope and noise, not bundled into a lint/type PR.
- No `--strict` mypy mode. The gap between "untyped" and "fully annotated" is a large
  annotation effort, not a bug backlog.
- No change to the existing coverage threshold.

## Files / modules

- `backend/pyproject.toml`: new, carries ruff, mypy, and pytest config.
- `backend/pytest.ini`: deleted, superseded by the above.
- `backend/requirements.txt`: `ruff` and `mypy` pinned to exact versions.
- `.github/workflows/ci.yml`: lint and type-check steps, plus workflow hardening.
- `backend/config/__init__.py`: explicit `__all__`.
- `backend/scrapers/sportsbooks/dk_engine.py`: `strict=True` zip.
- `backend/core/pipeline_runner.py`: tuple-unpack order fix.
- Scattered `isinstance` guards and type-narrowing fixes across `core/`, `scrapers/`, and
  `parsers/`.

## Test plan

- Full suite passes unchanged under the migrated pytest config, with identical coverage output.
- `ruff check .` and `mypy .` both exit clean from `backend/` under the pinned tool versions.
- No behavior change outside the two bug fixes above, both covered by the existing suite.
