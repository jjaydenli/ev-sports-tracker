# Config-only exemption in the arch-sync check

## Context

`scripts/check_arch_sync.sh` runs before a PR is opened and fails when a branch touches an
architecture path (`backend/scrapers`, `parsers`, `core`, `config`, `archive`, or
`docs/betting_odds/`) without a `project_context.md` change. #14 and #18 only added market or
subcategory ids under `backend/config/`. The check still demanded a doc edit, and there was nothing
true to write.

## Design decisions

- **A branch whose only architecture paths are under `backend/config/` needs no
  `project_context.md` change.** New ids extend tables the doc already describes in general terms.
- **`pipeline_sources.py` and `.env.example` stay covered, added or modified.** They decide which
  books run and which environment variables exist, and `project_context.md` documents both. Adding
  `pipeline_sources.py` still also requires a `README.md` change, as before.
- **The default is fail-safe.** Any architecture path outside `backend/config/` sets the same flag
  as before, so a new directory under `backend/` still demands a sync. Only listed config files are
  exempt, by path.
- **One flag, not a second pass.** `nonconfig` is set in the existing path loop beside `arch`, and
  only the `project_context.md` message reads it. The README rule is unchanged.

## Non-goals

- Exempting other doc rules. A config file that starts changing documented behaviour needs its own
  entry in the exception list.

## Files / modules

| Path | Change |
|------|--------|
| `scripts/check_arch_sync.sh` | `nonconfig` flag and the `backend/config/` exception list |

## Test plan

Cases run against the script in a scratch repo, each a branch off `main`:

- A `dk_subcategories.py` edit alone passes; beside a `backend/core` file it fails.
- `pipeline_sources.py` modified fails; added fails and also asks for `README.md`.
- An `.env.example` change fails.
