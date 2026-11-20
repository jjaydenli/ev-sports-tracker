"use client";

// The local board's run controls, rendered only when the page is the local board
// (isLocalBoard in lib/board.ts): Refresh, Auto-refresh (Stop while it runs), Shut down.

import { useRouter } from "next/navigation";
import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";

import { type Board, formatPacificTime } from "@/lib/board";

export const LOCAL_TIP =
  "Local board: shows the last ./ev run in this checkout. Refresh runs ./ev --top-n all " +
  "once; Auto-refresh reruns it until you press Stop or the time it shows. " +
  "Terminal runs show up on their own.";
const LOCAL_POLL_MS = 5_000;

type RunState = {
  running: boolean;
  looping: boolean;
  stoppable: boolean; // a run this page started: Refresh or Auto-refresh, not a terminal run
  boardRunId: string | null;
  loopEndsAt: string | null;
};

export type LocalRun = RunState & {
  stopping: boolean;
  shutDown: boolean;
  failed: boolean;
  refresh: () => void;
  autoRefresh: () => void;
  stop: () => void;
  shutDownServers: () => void;
};

async function readRunState(): Promise<RunState | null> {
  try {
    const res = await fetch("/api/local/run", { cache: "no-store" });
    if (!res.ok) return null;
    const body = await res.json();
    return {
      running: Boolean(body.running),
      looping: Boolean(body.looping),
      stoppable: Boolean(body.stoppable),
      boardRunId: body.board_run_id ?? null,
      loopEndsAt: body.loop_ends_at ?? null,
    };
  } catch {
    return null;
  }
}

/** POSTs a run control; the status, or null when the local API can't be reached. */
async function send(path: string): Promise<number | null> {
  try {
    return (await fetch(path, { method: "POST" })).status;
  } catch {
    return null;
  }
}

/**
 * The pill while a run is going or after Shut down: the board on screen is the last good one.
 * An auto-refresh names when it stops; ./loop checks that between runs, so past it the run
 * already going finishes first.
 */
export function localPillState(
  local: LocalRun,
  board: Board | null,
  nowMs: number,
): { tone: "running" | "off"; text: string } | null {
  const showing = board
    ? `showing board from ${formatPacificTime(board.generated_at, { seconds: true })}`
    : "no board yet";
  if (local.shutDown) {
    return { tone: "off", text: `Local board shut down · ${showing} · restart with npm run dev` };
  }
  if (local.looping) {
    const ends = local.loopEndsAt;
    if (!ends) return { tone: "running", text: `Auto-refreshing… · ${showing}` };
    if (nowMs >= Date.parse(ends)) {
      return { tone: "running", text: `Auto-refresh finishing its last run · ${showing}` };
    }
    const until = formatPacificTime(ends, { seconds: true, date: false });
    return { tone: "running", text: `Auto-refreshing until ${until} · ${showing}` };
  }
  if (local.running) return { tone: "running", text: `Running… · ${showing}` };
  return null;
}

/**
 * Null on the live board, which never polls. On the local board, polls the run state and
 * re-renders the page when a run ends or a new board lands (each auto-refresh run),
 * whoever started it. Polling stops after Shut down.
 */
export function useLocalRun(enabled: boolean): LocalRun | null {
  const router = useRouter();
  const [run, setRun] = useState<RunState>({
    running: false,
    looping: false,
    stoppable: false,
    boardRunId: null,
    loopEndsAt: null,
  });
  const [stopping, setStopping] = useState(false);
  const [shutDown, setShutDown] = useState(false);
  const [failed, setFailed] = useState(false);
  const seen = useRef<RunState | null>(null);

  const observe = useCallback(
    (next: RunState) => {
      const prev = seen.current;
      if (prev && ((prev.running && !next.running) || prev.boardRunId !== next.boardRunId)) {
        router.refresh();
      }
      seen.current = next;
      setRun(next);
      if (next.running) setFailed(false);
    },
    [router],
  );

  const poll = useCallback(async () => {
    const next = await readRunState();
    if (next) observe(next);
  }, [observe]);

  useEffect(() => {
    if (!enabled || shutDown) return;
    poll();
    const timer = setInterval(poll, LOCAL_POLL_MS);
    return () => clearInterval(timer);
  }, [enabled, shutDown, poll]);

  const start = useCallback(
    async (path: string, looping: boolean) => {
      const status = await send(path);
      // 409: a run is already going; the next poll says which kind.
      if (status === 202 || status === 409) {
        const boardRunId = seen.current?.boardRunId ?? null;
        const started = status === 202;
        observe({
          running: true,
          looping: looping && started,
          stoppable: started,
          boardRunId,
          loopEndsAt: null,
        });
        await poll(); // the stop time now, not at the next 5 s poll
      } else setFailed(true);
    },
    [observe, poll],
  );

  const stop = useCallback(async () => {
    setStopping(true);
    const status = await send("/api/local/stop");
    setStopping(false);
    if (status === 200 || status === 409) await poll();
    else setFailed(true);
  }, [poll]);

  const shutDownServers = useCallback(async () => {
    const status = await send("/api/local/shutdown");
    if (status === 202) setShutDown(true);
    else setFailed(true);
  }, []);

  if (!enabled) return null;
  return {
    ...run,
    stopping,
    shutDown,
    failed,
    refresh: () => start("/api/local/run", false),
    autoRefresh: () => start("/api/local/loop", true),
    stop,
    shutDownServers,
  };
}

/**
 * Refresh and Auto-refresh. While a run the page started is going, the button that started
 * it becomes its Stop. Fixed widths, so nothing moves under the cursor.
 */
export function LocalRunButtons({ local }: { local: LocalRun }) {
  if (local.shutDown) return null;
  const button = (slot: string, label: string, start: () => void, stops: boolean) => (
    <button
      type="button"
      className={`local-btn local-btn-${slot}`}
      disabled={stops ? local.stopping : local.running}
      onClick={stops ? local.stop : start}
    >
      {stops ? (local.stopping ? "Stopping…" : "Stop") : label}
    </button>
  );
  return (
    <div className="local-runs">
      {button("refresh", "Refresh", local.refresh, local.stoppable && !local.looping)}
      {button("auto", "Auto-refresh", local.autoRefresh, local.stoppable && local.looping)}
    </div>
  );
}

/** Shut down, behind a confirmation dialog; Cancel has focus, Esc or the backdrop cancels. */
export function ShutDownButton({ local }: { local: LocalRun }) {
  const dialog = useRef<HTMLDialogElement>(null);
  if (local.shutDown) return null;
  const close = () => dialog.current?.close();
  return (
    <>
      <button
        type="button"
        className="local-btn local-btn-danger local-shutdown"
        onClick={() => dialog.current?.showModal()}
      >
        Shut down
      </button>
      <dialog
        ref={dialog}
        className="confirm"
        aria-labelledby="confirm-title"
        onClick={(event) => event.target === dialog.current && close()}
      >
        <h2 id="confirm-title">Shut down the local board?</h2>
        <p>
          Stops both servers and any run the page started. Restart with <code>npm run dev</code>.
        </p>
        <div className="confirm-actions">
          <button type="button" className="local-btn" autoFocus onClick={close}>
            Cancel
          </button>
          <button
            type="button"
            className="local-btn local-btn-danger-fill"
            onClick={() => {
              close();
              local.shutDownServers();
            }}
          >
            Shut down
          </button>
        </div>
      </dialog>
    </>
  );
}

/** The local board's row: run buttons, the status pill, the failure note, Shut down. */
export function LocalBar({ local, children }: { local: LocalRun; children: ReactNode }) {
  return (
    <div className="local-bar">
      <LocalRunButtons local={local} />
      {children}
      {local.failed && <span className="pill-note">Couldn&apos;t reach the local API</span>}
      <ShutDownButton local={local} />
    </div>
  );
}
