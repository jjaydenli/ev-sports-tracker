import boardFields from "./board-fields.json";

/**
 * Engine row keys the page renders, by the name the page uses. The keys themselves live
 * once, in board-fields.json, which a backend test checks against a real engine row.
 */
export const F = boardFields;

/** One EV row as the engine wrote it. Rows are read only through {@link F}. */
export type BoardRow = Record<string, unknown>;

export type RunOutcome = "ok" | "empty" | "failed";

export type SourceHealth = {
  status: string | null;
  reason: string | null;
  prop_count: number | null;
  requests: number | null;
  blocked_requests: number | null;
};

export type Board = {
  run_id: string;
  generated_at: string;
  props: BoardRow[];
};

export type LatestRun = {
  run_id: string;
  generated_at: string;
  outcome: RunOutcome;
  exit_code: number;
  sources: Record<string, SourceHealth>;
};

export type BoardResponse = {
  board: Board | null;
  latest_run: LatestRun | null;
};

export const REVALIDATE_SECONDS = 300;

/**
 * Fetch the whole board. Throws on any failure: under ISR a thrown render keeps serving
 * the last good page, where a rendered error state would be cached in its place.
 */
export async function fetchBoard(): Promise<BoardResponse> {
  const apiUrl = process.env.BOARD_API_URL;
  if (!apiUrl) {
    throw new Error("BOARD_API_URL is not set");
  }
  const response = await fetch(`${apiUrl.replace(/\/+$/, "")}/api/board`, {
    next: { revalidate: REVALIDATE_SECONDS },
  });
  if (!response.ok) {
    throw new Error(`board API returned HTTP ${response.status}`);
  }
  return (await response.json()) as BoardResponse;
}

export function num(row: BoardRow, key: string): number | null {
  const value = row[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function str(row: BoardRow, key: string): string | null {
  const value = row[key];
  return typeof value === "string" && value !== "" ? value : null;
}

export function bool(row: BoardRow, key: string): boolean {
  return row[key] === true;
}

export const DASH = "–";

export function formatOdds(value: number | null): string {
  if (value === null) return DASH;
  return value > 0 ? `+${value}` : `${value}`;
}

export function formatPct(value: number | null, digits = 1): string {
  return value === null ? DASH : `${value.toFixed(digits)}%`;
}

const BOOK_NAMES: Record<string, string> = {
  betr: "Betr",
  dk: "DraftKings",
  fd: "FanDuel",
  espn: "ESPN",
};

/** "dk:NBA" → "DraftKings"; unknown sources fall back to the raw key. */
export function sourceBookName(sourceKey: string): string {
  const book = sourceKey.split(":")[0];
  return BOOK_NAMES[book] ?? sourceKey;
}

const TIME_ZONE = "America/Los_Angeles";

export function formatPacificTime(iso: string): string {
  const text = new Intl.DateTimeFormat("en-US", {
    timeZone: TIME_ZONE,
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(iso));
  return `${text} PT`;
}
