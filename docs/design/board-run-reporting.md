# One row per prop, and runs that say why they failed

## Context

The board is about to be read by people who did not run it: a scheduled job pushes each run to a
hosted page. Four behaviours that were tolerable at a terminal would mislead there. A plain `./ev`
(no `--min-ev`) printed both legs of every two-way market. A dead Betr token deleted the previous
board before the run stopped. A DraftKings scrape blocked by Akamai reported `no_events`, which is
what a night with no games looks like. An empty board logged a green success line.

## Design decisions

- **One EV row per DFS prop, chosen inside the engine loop.** `_pick_side` in `core/engine.py`
  keeps the higher-EV side the DFS book allows. Both sides of a Betr prop share one breakeven, so
  that is the side with the higher fair probability, and no cross-row dedup key is needed. Choosing
  before the `--min-ev` filter gives the same output as dedup after it, since the kept side passes
  whenever the dropped one would.
- **An exact 50/50 de-vig becomes one `O/U` row.** Picking a side there would be arbitrary.
  Tolerance is `1e-9` on the unrounded fair probabilities, so only a truly symmetric sharp line
  collapses.
- **Betr auth fails fast, before anything is wiped.** Without Betr there is no EV, so scraping the
  books anyway buys nothing. The check moves ahead of `wipe_files`, so the last good board stays
  on disk. Both auth failure paths (refresh rejected, token rejected by validation) are caught, and
  the run prints a re-capture hint.
- **Coverage records why a run stopped.** An auth failure writes `scrape_coverage.json` with each
  `betr:<league>` entry `failed`, `reason: "auth"`. A scheduled run can read the reason instead of
  parsing logs.
- **A DraftKings block is counted from final responses, not attempts.** A response hook on the
  scrape client (`DkBlockLedger`) keeps the last status per URL. A request that 403s and then
  succeeds on retry is served; one still 403/429 after the retry budget is blocked. Using the
  client the engine already owns means no fetch function signature changes.
- **No props plus any block is `failed`, `reason: "blocked"`.** A partial block stays `ok`, with
  `requests` and `blocked_requests` in coverage and `blocked=N/M` on the summary line, so a drop in
  DraftKings props can be told apart from games ending.
- **An empty board is a warning with a reason.** Either nothing reached `--min-ev`, or no Betr prop
  resolved to an EV-eligible sharp line.

## Non-goals

- Block counting for FanDuel or ESPN. Neither has shown an IP block; their coverage fields stay
  `null`.
- Canonicalizing DraftKings team codes. EV rows take `game` from the Betr prop, so a sharp book's
  `game` string only reaches its normalized board JSON.

## Files / modules

| Path | Change |
|------|--------|
| `backend/core/engine.py` | `_pick_side`, one append per prop |
| `backend/core/pipeline_runner.py` | auth before wipe, auth-failure coverage, `blocked=N/M` in the summary |
| `backend/core/ev_pipeline.py` | `_empty_board_reason` |
| `backend/core/pipeline_scrape.py`, `core/scrape_result.py` | `blocked` status mapping, `requests` / `blocked_requests` |
| `backend/scrapers/sportsbooks/dk_api.py`, `dk_engine.py` | `DkBlockLedger` and its hook |
| `backend/config/team_abbrev.py` | NBA full names in Betr's NBA codes |

## Test plan

- Side pick: hand-computed EV for -140/+120 (+0.0166, both orientations) and -115/-105 (-0.0346);
  -115/-115 gives one `O/U` row at 50.0%. Golden snapshots lose five losing-leg rows and nothing
  else.
- Auth: both failure paths leave the prior `ev_opportunities.json` and normalized boards in place
  and write `reason: "auth"` coverage.
- DraftKings: a slate block and a markets-only block both report `blocked`; a partial block stays
  `ok` with counts matching the transport's own tally. Counting any URL that ever saw a 403 fails
  the retry test.
