# Serializing concurrent `./ev` writers on `data/processed`

## Context

`run_refresh` wipes, scrapes, and persists board files under `data/processed`, then a
downstream `run_ev_scan` call loads them back by `run_id` to assert freshness
(`assert_run_id` / the `expected_run_id` check in `load_comparison_inputs`). Nothing
prevented two `./ev` processes from running against the same `data/processed` directory at
the same time. When they overlapped, each run's wipe/scrape/persist sequence interleaved
with the other's: one process could persist its board between the other's wipe and load,
so a normalized-board read would see a `run_id` that belonged to the wrong run and hard-fail
with a `run_id mismatch` error mid-pipeline.

This is a plain shared-mutable-state race — two writers, one resource, no coordination — not
a scraping or matching bug. It surfaces today from two overlapping `./ev` invocations
(directly, or indirectly via two concurrent `./loop` instances each firing `./ev` on its own
schedule), but the same shape of collision applies to any deployment where more than one
process can trigger a refresh independently (e.g. a scheduled refresh and an on-demand
refresh firing close together).

## Design decisions

1. **Exclusive lock scoped to the run, not the process.** `pipeline_run_lock(data_dir)` is a
   context manager wrapping `fcntl.flock` on a dedicated lock file
   (`data_dir/.pipeline_run.lock`). It is acquired non-blocking first; on contention it logs
   a warning and falls back to a blocking acquire, so a second `./ev` waits for the first to
   finish rather than failing outright. The lock is released in a `finally`, so it cannot be
   held past a crash inside the run.

2. **OS-level advisory lock, not an application-level flag.** `flock` is chosen over e.g. a
   sentinel file checked with `if exists` because it is atomic, held per open file
   description (safe across threads and processes on the same host), and automatically
   released if a process dies — no stale-lock cleanup logic needed.

3. **Scope: single machine.** `flock` only coordinates processes sharing one kernel. That
   matches the current and only deployment target (one process, one host). No
   network-shared locking primitive is introduced, since nothing runs on more than one host
   today.

4. **Atomic board writes.** `save_wrapped_board` now writes to a `pid`-suffixed temp file in
   the same directory, `fsync`s it, then `os.replace`s it over the target path, instead of
   writing the target path directly. `os.replace` is an atomic rename on POSIX, so a
   concurrent reader (or a lock-free legacy caller) can never observe a partially written
   board — it sees either the old file or the new one, never a torn write.

5. **Blocking, not timeout-and-fail.** The lock blocks the caller until it is free rather
   than raising after a timeout. Every current caller (`./ev`, `./loop`) is a foreground CLI
   invocation where waiting for the prior run to finish is the correct behavior; nothing
   today needs a "someone else is already refreshing" response instead of waiting.

## Non-goals

- No distributed/multi-host locking (Redis, Postgres advisory locks, etc.) — nothing runs on
  more than one host today. `pipeline_run_lock`'s call sites take a lock object via a single
  context-manager interface, so swapping the backend later doesn't change any caller.
- No non-blocking "reject if busy" mode — no current caller needs it; today's callers are
  synchronous CLI processes for which waiting is correct.
- No change to what gets scraped, matched, or ranked — this only serializes writes to shared
  on-disk state.

## Files / modules

### `core/pipeline_artifacts.py`
- `pipeline_run_lock(data_dir) -> Iterator[None]`: `contextmanager` wrapping `fcntl.flock`,
  non-blocking attempt then blocking fallback with a warning log.
- `save_wrapped_board`: writes to a temp file + `fsync` + `os.replace` instead of writing the
  target path in place.

### `core/pipeline_runner.py`
- `run_refresh` acquires `pipeline_run_lock(data_path)` for the duration of the run via an
  `ExitStack`, released in the existing `finally` alongside `timer.log_summary()`.

## Test plan

- `test_run_refresh_serializes_overlapping_writers`: two `run_refresh` calls against the same
  `tmp_path` started on separate threads. Both must return `0`, and the resulting board must
  be internally consistent (a real `run_id`, non-empty props) — i.e. no interleaved
  wipe/persist/load. Verified to fail without the lock and pass with it.
- Full unit suite otherwise unaffected — no scraping, matching, or ranking behavior changed.
