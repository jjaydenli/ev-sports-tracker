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
   between runs. Overridable via loop-owned `--timeout SECS` (default 300), validated as a
   positive integer and stripped before forwarding.

2. **Fatal-on-failure, not retry.** A non-zero `./ev` exit is treated as fatal: the loop prints
   the tail of the captured stderr and aborts. Bad arguments do not fix themselves on retry, and
   without this a fast-failing `./ev` would busy-spin the table until the wall-clock cap. A small
   `MIN_INTERVAL` floor additionally paces the loop so an unexpectedly instant successful run
   (e.g. an offline slate) cannot spin either.

3. **Argument forwarding + defaults.** Every non-loop argument forwards to `./ev` unchanged.
   `--timeout` is the only loop-owned duration flag. With no league flag, `./ev` runs all configured
   leagues (NBA, MLB, WNBA). Filter with `--mlb`, `--nba`, `--wnba`, and/or `--leagues mlb,wnba`
   (shorthand unions with `--leagues`). When `--min-ev` is omitted, `./loop` forwards no threshold
   (full board, still `--top-n`-capped), matching `./ev`'s own behavior. Pass `--min-ev X` to
   filter (negative values include near-breakeven rows per the min-ev ADR).

4. **`--min-ev` pass-through.** When set, forwarded to `./ev`, which filters
   `ev_opportunities.json` to rows with `ev >=` threshold. When omitted, the file is unfiltered
   (still `--top-n`-capped). `./loop` applies its own toast eligibility on top: `plus_ev`
   (`ev > 0`) and, when `--min-ev` was passed, `ev >=` that threshold — the JSON is not assumed
   pre-filtered by a default.

5. **Table-only display.** `./ev`'s stderr is redirected to a temporary log (surfaced only on
   failure) so log noise never reaches the table view. After each run the ranked table is
   re-rendered from the persisted opportunities file via `format_ev_opportunities_table` (EV-tier
   and stack coloring on). Rows for props not yet notified this run are highlighted (bold yellow
   on non-Stack cells); everything else prints without highlight. Only a one-line iteration/elapsed
   header is added.

6. **Notify only on new matches.** Toast iff `new ∧ plus_ev ∧ (min_ev is None ∨ ev >= min_ev)`.
   `min_ev` comes from the `--min-ev` value captured at parse time (`MIN_EV_VALUE` env var,
   empty when omitted → `None` in the embedded python). A per-run set of prop keys
   (`player|market|line|side|league`) tracks what has already been notified; a toast fires only for
   keys not seen earlier in the run that also pass the rule above. State is held in a temp file
   reset on each invocation.

7. **Toast content.** Title `EV alert (N new, M total)`; body is the top new prop as
   `<player> <side> <line> <market>` with underscores in `market` turned into spaces
   (e.g. `Shohei Ohtani over 0.5 home runs`), with `(+K more)` appended when several are new.

8. **OS-agnostic notification backend.** The delivery backend is detected once at startup and the
   rest of the loop is platform-independent:
   - **WSL** — a Windows toast via `powershell.exe` and `Windows.UI.Notifications`
     (`ToastText02` template) under a registered AppId, so it reliably surfaces with no module
     install. WSL is Linux with a Microsoft kernel, so it is detected before the generic-Linux
     branch.
   - **macOS** — prefer `terminal-notifier` when on `PATH` (own Notification Center identity;
     `brew install terminal-notifier`). Fall back to `osascript` `display notification` via
     `on run argv` + Glass sound. Sequoia often drops bare `osascript` toasts (exit 0) when
     Script Editor lacks Notifications permission; stderr matching `notification center invalid`
     is treated as failure, with a one-time install/permission hint.
   - **native Linux** — `notify-send` (libnotify) when present.
   - **none found** — the loop still prints the table and warns once.

   Prop keys are appended to the per-run notified set only after a successful toast (or when
   there is no backend), so a silent macOS drop can retry on the next iteration.

   The script targets bash 3.2 for macOS compatibility (no `mapfile`; portable read for toast
   title/body/keys).

## Non-goals

- No changes to the pipeline runner, EV scan math, or any scraper/parser/engine beyond table output wiring.
- No persistent / actionable toasts (macOS path may play Glass via terminal-notifier / osascript).
- Not scheduled or daemonized — a foreground command the user starts manually.
- Bundling `terminal-notifier` — optional host install only.

## Files / modules

- **`loop`** (new, repo root, executable) — the whole feature.
- Reuses read-only: `ev` (bootstrap pattern), `core/ev_display.format_ev_table_header` /
  `format_ev_opportunity_row`, and the persisted `data/processed/ev_opportunities.json` schema
  (`{run_id, generated_at, props[]}`; each prop has `player, league, market, line, side, ev,
  ev_pct`).
- Reuses pass-through: the pipeline runner's `--min-ev` and league flags.

## Test plan

- Backend suite unaffected (no Python changed).
- Invalid `--timeout` (non-numeric, missing value) exits with a clear message, not a shell
  crash.
- An unrecognized `./ev` argument aborts after one run with the underlying error, rather than
  spinning the table.
- Against a live slate: clean tables with no log noise; new-prop rows highlighted; re-appearing
  props are not re-notified within the same run; exits at the wall-clock cap.
- A qualifying prop fires exactly one desktop toast on the host's detected backend.
- On macOS without `terminal-notifier`, a silent `osascript` NC failure does not mark the prop
  notified (retries next iteration) and prints the one-time hint once.
