"use client";

// The local board's run trigger, rendered only when the page is the local board
// (isLocalBoard in lib/board.ts).

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { type Board, formatPacificTime } from "@/lib/board";

export const LOCAL_TIP =
  "Local board: shows the last ./ev run in this checkout. Refresh runs ./ev --top-n all " +
  "here; terminal runs show up on their own.";
const LOCAL_RUN_URL = "/api/local/run";
const LOCAL_POLL_MS = 5_000;

export type LocalRun = { running: boolean; failed: boolean; start: () => void };

async function localRunning(): Promise<boolean | null> {
  try {
    const res = await fetch(LOCAL_RUN_URL, { cache: "no-store" });
    if (!res.ok) return null;
    return Boolean((await res.json()).running);
  } catch {
    return null;
  }
}

/** The pill while a run holds the lock: the board on screen is the last good one. */
export function runningPillState(board: Board | null): { tone: "running"; text: string } {
  const showing = board
    ? `showing board from ${formatPacificTime(board.generated_at, { seconds: true })}`
    : "no board yet";
  return { tone: "running", text: `Running… · ${showing}` };
}

/**
 * Null on the live board, which never polls. On the local board, polls the run state and
 * re-renders the page when a run ends, whoever started it.
 */
export function useLocalRun(enabled: boolean): LocalRun | null {
  const router = useRouter();
  const [state, setState] = useState<Omit<LocalRun, "start"> | null>(
    enabled ? { running: false, failed: false } : null,
  );
  const wasRunning = useRef(false);

  const observe = useCallback(
    (running: boolean) => {
      if (wasRunning.current && !running) router.refresh();
      wasRunning.current = running;
      setState((prev) => ({ running, failed: running ? false : (prev?.failed ?? false) }));
    },
    [router],
  );

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    const poll = async () => {
      const running = await localRunning();
      if (!cancelled && running !== null) observe(running);
    };
    poll();
    const timer = setInterval(poll, LOCAL_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [enabled, observe]);

  const start = useCallback(async () => {
    let ok = false;
    try {
      const res = await fetch(LOCAL_RUN_URL, { method: "POST" });
      ok = res.status === 202 || res.status === 409; // 409: a run is already going
    } catch {}
    if (ok) observe(true);
    else setState({ running: false, failed: true });
  }, [observe]);

  return state && { ...state, start };
}

/** Refresh, grayed out while a run is going, and a note when the start request fails. */
export function LocalRunControls({ local }: { local: LocalRun }) {
  return (
    <>
      <button type="button" className="pill-refresh" disabled={local.running} onClick={local.start}>
        Refresh
      </button>
      {local.failed && <span className="pill-note">Couldn&apos;t reach the local API</span>}
    </>
  );
}
