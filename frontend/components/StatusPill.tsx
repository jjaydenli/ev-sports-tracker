"use client";

import { useEffect, useState } from "react";

import { LOCAL_TIP, LocalBar, localPillState, useLocalRun } from "@/components/LocalRunControls";
import {
  type Board,
  type LatestRun,
  formatPacificTime,
  sourceBookName,
} from "@/lib/board";

type Tone = "green" | "amber" | "red" | "running" | "off";

const STALE_AFTER_MS = 18 * 60 * 60 * 1000;

// Mirrors the external cron that triggers .github/workflows/live-board.yml; keep in step.
const SCHEDULE_TIP =
  "Updates 4x daily at 9:35, 12:35, 3:35 and 6:35 PT. A fixed schedule keeps request " +
  "volume low so the sportsbooks don't rate-limit the scraper.";

/**
 * One label per distinct failure, named by book so leagues fold together: "Betr login",
 * "DraftKings blocked", "theScore Bet unavailable".
 */
function failureLabels(run: LatestRun): string[] {
  const labels: string[] = [];
  for (const [key, health] of Object.entries(run.sources)) {
    if (health.status !== "failed") continue;
    const book = sourceBookName(key);
    let label = `${book} unavailable`;
    if (health.reason === "auth") label = "Betr login";
    else if (health.reason === "blocked") label = `${book} blocked`;
    if (!labels.includes(label)) labels.push(label);
  }
  return labels;
}

function formatAge(ms: number): string {
  const minutes = Math.floor(ms / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export function pillState(
  run: LatestRun | null,
  board: Board | null,
  nowMs: number | null,
  seconds = false,
): { tone: Tone; text: string } {
  const time = (iso: string) => formatPacificTime(iso, { seconds });
  const showing = board ? ` · showing board from ${time(board.generated_at)}` : "";
  if (!run) {
    return { tone: "amber", text: "No scrape runs yet" };
  }
  const failures = failureLabels(run);
  if (run.outcome === "failed") {
    const why = failures.length ? `: ${failures[0]}` : "";
    return { tone: "red", text: `Last scrape failed${why}${showing}` };
  }
  if (run.outcome === "empty") {
    return { tone: "amber", text: `Latest run found no props${showing}` };
  }
  if (failures.length) {
    return { tone: "amber", text: `Partial prices: ${failures.join(", ")}${showing}` };
  }
  const scrapedAt = Date.parse(run.generated_at);
  const at = time(run.generated_at);
  if (nowMs === null) {
    return { tone: "green", text: `Scraped ${at}` };
  }
  const age = formatAge(nowMs - scrapedAt);
  if (nowMs - scrapedAt > STALE_AFTER_MS) {
    return { tone: "amber", text: `Board is ${age.replace(" ago", "")} old · ${at}` };
  }
  return { tone: "green", text: `Scraped ${age} · ${at}` };
}

/**
 * Client component so the relative age stays current inside cached HTML. The server
 * render (and the first client render, to match it) shows the absolute time only. `local`
 * (the page's `isLocalBoard()`) puts the pill in the local board's row of run controls and
 * adds seconds; the live board has neither and never polls.
 */
export function StatusPill({
  run,
  board,
  local: isLocal,
}: {
  run: LatestRun | null;
  board: Board | null;
  local: boolean;
}) {
  const [nowMs, setNowMs] = useState<number | null>(null);
  useEffect(() => {
    setNowMs(Date.now());
    const timer = setInterval(() => setNowMs(Date.now()), 60_000);
    return () => clearInterval(timer);
  }, []);

  const local = useLocalRun(isLocal);
  const { tone, text } =
    (local && localPillState(local, board, Date.now())) ?? pillState(run, board, nowMs, isLocal);
  const pill = (
    <p className={`pill pill-${tone}`} role="status">
      <span className="pill-dot" aria-hidden="true" />
      {text}
      <button
        type="button"
        className="pill-info"
        aria-label={local ? "About the local board" : "Refresh schedule"}
        data-tip={local ? LOCAL_TIP : SCHEDULE_TIP}
      >
        <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
          <circle cx="8" cy="8" r="6.75" fill="none" stroke="currentColor" strokeWidth="1.5" />
          <circle cx="8" cy="4.9" r="1" fill="currentColor" />
          <path d="M8 7.2v4.4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
      </button>
    </p>
  );
  return local ? <LocalBar local={local}>{pill}</LocalBar> : pill;
}
