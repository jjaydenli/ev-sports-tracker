# `./loop` — timed EV run loop with desktop toast alerts

## Context

`./ev` performs a single scrape → EV pass and emits a lot of log output (scrape coverage,
per-source detail, ranked-plays block, run-diff summary) to stderr. For live monitoring a user
wants to re-run it continuously for a short window and be pinged the moment a qualifying edge
appears, without watching the terminal or wading through log noise.

Nothing else loops `./ev` or notifies the host OS. `./loop` is a thin repo-root orchestration
wrapper around `./ev` — **no backend Python behavior changes**. It mirrors `./ev`'s bootstrap
(resolve repo root, `cd backend`, activate the venv if present), re-runs `./ev` back-to-back for a
bounded wall-clock window, re-renders only the ranked table, and fires a desktop toast the first
time a prop crosses the `--min-ev` threshold within that run.

## Design decisions

1. **Duration model.** The loop runs `./ev` back-to-back — the next iteration starts when the
   prior process exits. After each run it checks elapsed wall-clock and stops once
   `>= LOOP_SECONDS` (default 300). An in-flight run always finishes; the cap is only checked
   between runs. Overridable via the loop-owned `--loop-seconds N` flag, which is validated as a
   positive integer and stripped before forwarding.

2. **Fatal-on-failure, not retry.** A non-zero `./ev` exit is treated as fatal: the loop prints
   the tail of the captured stderr and aborts. Bad arguments do not fix themselves on retry, and
   without this a fast-failing `./ev` would busy-spin the table until the wall-clock cap. A small
   `MIN_INTERVAL` floor additionally paces the loop so an unexpectedly instant successful run
   (e.g. an offline slate) cannot spin either.

3. **Argument forwarding + default slate.** Every non-loop argument forwards to `./ev` unchanged.
   `--loop-seconds` is the only loop-owned flag. If the forwarded arguments contain no league flag,
   `--mlb` is injected. If `--min-ev` is omitted, `--min-ev 0.02` is injected.

4. **`--min-ev` is a single source of truth.** It is a pass-through to `./ev` (a fraction; `0.02`
   = 2%). It both filters the opportunities file and defines the notify threshold — the loop adds
   no separate threshold logic.

5. **Table-only display.** `./ev`'s stderr is redirected to a temporary log (surfaced only on
   failure) so log noise never reaches the table view. After each run the ranked table is
   re-rendered from the persisted opportunities file, reusing the existing table formatter. Rows
   for props not yet notified this run are highlighted (bold yellow); everything else prints plain.
   Only a one-line iteration/elapsed header is added.

6. **Notify only on new matches.** Because the opportunities file is already filtered by
   `--min-ev`, every prop in it qualifies. A per-run set of prop keys
   (`player|market|line|side|league`) tracks what has already been notified; a toast fires only for
   keys not seen earlier in the run. State is held in a temp file reset on each invocation.

7. **Toast content.** Title `EV alert (N new, M total)`; body is the top new prop
   (`<player> <market> <line> <side> +<ev_pct>%`), with `(+K more)` appended when several are new.

8. **OS-agnostic notification backend.** The delivery backend is detected once at startup and the
   rest of the loop is platform-independent:
   - **WSL** — a Windows toast via `powershell.exe` and `Windows.UI.Notifications`
     (`ToastText02` template) under a registered AppId, so it reliably surfaces with no module
     install. WSL is Linux with a Microsoft kernel, so it is detected before the generic-Linux
     branch.
   - **macOS** — `osascript` `display notification` (built in).
   - **native Linux** — `notify-send` (libnotify) when present.
   - **none found** — the loop still prints the table and warns once.

   The script targets bash 3.2 for macOS compatibility (no `mapfile`; portable two-line read for
   toast content).

## Non-goals

- No changes to the pipeline runner, EV pipeline, display formatter, or any scraper/parser/engine.
- No sound / persistent / actionable toasts.
- Not scheduled or daemonized — a foreground command the user starts manually.
- No reconciliation of `>=` vs `>` beyond reusing the pipeline's existing `--min-ev` semantics.

## Files / modules

- **`loop`** (new, repo root, executable) — the whole feature.
- Reuses read-only: `ev` (bootstrap pattern), `core/ev_display.format_ev_table_header` /
  `format_ev_opportunity_row`, and the persisted `data/processed/ev_opportunities.json` schema
  (`{run_id, generated_at, props[]}`; each prop has `player, league, market, line, side, ev,
  ev_pct`).
- Reuses pass-through: the pipeline runner's `--min-ev` and league flags.

## Test plan

- Backend suite unaffected (no Python changed).
- Invalid `--loop-seconds` (non-numeric, missing value) exits with a clear message, not a shell
  crash.
- An unrecognized `./ev` argument aborts after one run with the underlying error, rather than
  spinning the table.
- Against a live slate: clean tables with no log noise; new-prop rows highlighted; re-appearing
  props are not re-notified within the same run; exits at the wall-clock cap.
- A qualifying prop fires exactly one desktop toast on the host's detected backend.
