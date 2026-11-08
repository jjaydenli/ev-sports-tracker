"use client";

import { useEffect, useState } from "react";

import {
  type Board,
  type LatestRun,
  formatPacificTime,
  sourceBookName,
} from "@/lib/board";

type Tone = "green" | "amber" | "red";

const STALE_AFTER_MS = 18 * 60 * 60 * 1000;

/** One label per distinct failure: "Betr login", "DraftKings blocked", or the source key. */
function failureLabels(run: LatestRun): string[] {
  const labels: string[] = [];
  for (const [key, health] of Object.entries(run.sources)) {
    if (health.status !== "failed") continue;
    let label = key;
    if (health.reason === "auth") label = "Betr login";
    else if (health.reason === "blocked") label = `${sourceBookName(key)} blocked`;
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
): { tone: Tone; text: string } {
  const showing = board ? ` · showing board from ${formatPacificTime(board.generated_at)}` : "";
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
  const at = formatPacificTime(run.generated_at);
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
 * render (and the first client render, to match it) shows the absolute time only.
 */
export function StatusPill({ run, board }: { run: LatestRun | null; board: Board | null }) {
  const [nowMs, setNowMs] = useState<number | null>(null);
  useEffect(() => {
    setNowMs(Date.now());
    const timer = setInterval(() => setNowMs(Date.now()), 60_000);
    return () => clearInterval(timer);
  }, []);

  const { tone, text } = pillState(run, board, nowMs);
  return (
    <p className={`pill pill-${tone}`} role="status">
      <span className="pill-dot" aria-hidden="true" />
      {text}
    </p>
  );
}
