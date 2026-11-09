import boardFields from "./board-fields.json";
import booksJson from "./books.json";

/**
 * Engine row keys the page renders, by the name the page uses. The keys themselves live
 * once, in board-fields.json, which a backend test checks against a real engine row.
 */
export const F = boardFields;

/** The product's name: tab title, page heading, error page. */
export const SITE_NAME = "AlphaOdds";

/** The header's GitHub button. */
export const SOURCE_URL = "https://github.com/jjaydenli/ev-sports-tracker";

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
  // League -> team code -> full names. Absent until the API is redeployed.
  team_names?: Record<string, Record<string, string[]>>;
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

/** "+1.30%": a signed percent, for EV. */
export function formatSignedPct(value: number | null, digits = 2): string {
  if (value === null) return DASH;
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

/**
 * A probability (0–100) as American odds: 54.55 → −120, 47.62 → +110. The page's twin of
 * the backend's `implied_to_american`, which it cannot call.
 */
export function pctToAmerican(pct: number | null): number | null {
  if (pct === null || pct <= 0 || pct >= 100) return null;
  return Math.round(pct >= 50 ? (-100 * pct) / (100 - pct) : (100 * (100 - pct)) / pct);
}

/** American odds as the probability (0–100) they imply, vig included: −135 → 57.45. */
export function americanToPct(odds: number | null): number | null {
  if (odds === null || odds === 0) return null;
  return odds < 0 ? (100 * -odds) / (-odds + 100) : (100 * 100) / (odds + 100);
}

/** A two-way price's hold (the book's margin), in points; null when a side is missing. */
export function holdPct(over: number | null, under: number | null): number | null {
  const o = americanToPct(over);
  const u = americanToPct(under);
  return o === null || u === null ? null : o + u - 100;
}

/** Hit % minus Betr's breakeven, in points: the edge the colour grades and EV % states. */
export function edgePts(row: BoardRow): number | null {
  const hit = num(row, F.hitPct);
  const breakeven = num(row, F.betrBreakevenPct);
  return hit === null || breakeven === null ? null : hit - breakeven;
}

/** Hit % fill step: above breakeven green (under 1 pt, under 2.5, beyond); within 1 pt below,
 * orange ("near"); further below, or unpriced, no fill. Red is kept for under picks and LIVE. */
export type EdgeStep = "e3" | "e2" | "e1" | "near" | null;

export function edgeStep(edge: number | null): EdgeStep {
  if (edge === null || edge <= -1) return null;
  if (edge <= 0) return "near";
  if (edge < 1) return "e1";
  if (edge < 2.5) return "e2";
  return "e3";
}

// ---- books ----

export type FieldName = keyof typeof F;

/** One sportsbook or DFS app. Books with `over`/`under` get a price column. */
export type Book = {
  /** Source key prefix in run health (`dk` in `dk:NBA`). */
  key: string;
  name: string;
  /** The name the engine writes into `sharp_books`, when it differs from `name`. */
  sharpName?: string;
  /** Path under `public/`; the monogram stands in when null. */
  logo: string | null;
  monogram?: string;
  over?: FieldName;
  under?: FieldName;
};

/** The book registry, in column order. */
export const BOOKS = booksJson as Book[];

export const PRICED_BOOKS = BOOKS.filter((book) => book.over && book.under);

function bookByKey(key: string): Book | undefined {
  return BOOKS.find((book) => book.key === key);
}

export const BETR = bookByKey("betr") as Book;

/** "dk:NBA" → "DraftKings"; unknown sources fall back to the raw key. */
export function sourceBookName(sourceKey: string): string {
  return bookByKey(sourceKey.split(":")[0])?.name ?? sourceKey;
}

/** A `sharp_books` entry ("ESPN") as its display name ("theScore Bet"). */
export function sharpBookName(sharpName: string): string {
  return BOOKS.find((book) => book.sharpName === sharpName)?.name ?? sharpName;
}

export type Prices = { over: number | null; under: number | null };

export function bookPrices(row: BoardRow, book: Book): Prices {
  return {
    over: book.over ? num(row, F[book.over]) : null,
    under: book.under ? num(row, F[book.under]) : null,
  };
}

export function hasPrices({ over, under }: Prices): boolean {
  return over !== null || under !== null;
}

// ---- words ----

const MARKET_WORDS: Record<string, string> = {
  points: "Points",
  rebounds: "Rebounds",
  assists: "Assists",
  threes: "Threes",
  "pts+reb": "Pts + Reb",
  "pts+ast": "Pts + Ast",
  "reb+ast": "Reb + Ast",
  pra: "Pts + Reb + Ast",
  hits: "Hits",
};

/** Filter menus list leagues in this order; any other league follows, A–Z. */
export const LEAGUE_ORDER: readonly string[] = ["NBA", "NFL", "NHL", "MLB"];

/**
 * Each league's markets in the filter menu, by market key; any other market follows, A–Z.
 * Fixed rather than by prop count, so the list does not reshuffle on every refresh.
 */
export const MARKET_ORDER: Readonly<Record<string, readonly string[]>> = {
  NBA: ["points", "rebounds", "assists", "pra", "pts+reb", "pts+ast", "reb+ast", "threes"],
  MLB: ["hits"],
};

/** A value's place in one of the orders above; unlisted values all tie, after the listed ones. */
export function orderRank(order: readonly string[] | undefined, value: string): number {
  const i = order?.indexOf(value) ?? -1;
  return i < 0 ? Number.MAX_SAFE_INTEGER : i;
}

/** "pts+reb" → "Pts + Reb"; an unknown market shows its raw key. */
export function marketWords(market: string | null): string {
  if (market === null) return DASH;
  return MARKET_WORDS[market] ?? market;
}

const LINE_SOURCE_WORDS: Record<string, string> = {
  exact: "DraftKings line at Betr's number",
  dk_alt: "DraftKings alternate line at Betr's number",
  fd_exact: "FanDuel line at Betr's number",
  fd_alt: "FanDuel alternate line at Betr's number",
  espn_exact: "theScore Bet line at Betr's number",
  espn_alt: "theScore Bet alternate line at Betr's number",
  dk_interpolated: "Fair price blended from the DraftKings lines either side of Betr's number",
  milestone_exact: "DraftKings milestone ladder (e.g. 25+), not a two-way line",
};

function sharpBooks(row: BoardRow): string[] {
  const value = row[F.sharpBooks];
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];
}

/** Where the fair price came from, in words; an unknown source shows its raw key. */
export function lineSourceWords(row: BoardRow): string {
  const source = str(row, F.lineSource);
  if (source === null) return DASH;
  if (source === "multi_book_consensus") {
    const books = sharpBooks(row).map(sharpBookName);
    return books.length
      ? `Consensus of ${books.join(" and ")}, each at Betr's number`
      : "Consensus of sportsbooks at Betr's number";
  }
  return LINE_SOURCE_WORDS[source] ?? source;
}

/** "u7.5": the pick's side letter and Betr's line. */
export function pickLine(row: BoardRow): string {
  const side = str(row, F.side);
  const letter = side === "over" ? "o" : side === "under" ? "u" : "";
  return `${letter}${num(row, F.line) ?? DASH}`;
}

export type MatchupPart = { text: string; own: boolean };

/**
 * "PHI@CHI" with the player's team marked: [PHI (own), " @ ", CHI]. Falls back to the raw
 * game when it has no "@", and to the league when there is no game.
 */
export function matchup(row: BoardRow): MatchupPart[] {
  const game = str(row, F.game);
  if (game === null) return [{ text: str(row, F.league) ?? "", own: false }];
  const sides = game.split("@");
  if (sides.length !== 2) return [{ text: game, own: false }];
  const team = str(row, F.team);
  const [away, home] = sides.map((s) => s.trim());
  return [
    { text: away, own: away === team },
    { text: " @ ", own: false },
    { text: home, own: home === team },
  ];
}

/**
 * The expanded row's "why" sentence: a verdict and the two numbers it compares.
 * "Fair chance of the under is 54.08%; Betr needs 54.55% to break even."
 */
export function whySentence(row: BoardRow): { verdict: string; fair: string; need: string } | null {
  const hit = num(row, F.hitPct);
  const breakeven = num(row, F.betrBreakevenPct);
  const edge = edgePts(row);
  if (hit === null || breakeven === null || edge === null) return null;
  return {
    verdict: edge > 0 ? "+EV" : "Not +EV",
    fair: formatPct(hit, 2),
    need: formatPct(breakeven, 2),
  };
}

/** "6.2% vig": a book's hold on its two-way price, in the bettor's word. */
export function vigWords(prices: Prices): string | null {
  const hold = holdPct(prices.over, prices.under);
  return hold === null ? null : `${hold.toFixed(1)}% vig`;
}

/** One-sided prices make the fair probability an estimate; say so when the row flags it. */
export function oneSidedCaveat(row: BoardRow): string | null {
  return bool(row, F.notTrueDevig) || bool(row, F.undisclosedVigCaveat)
    ? "One-sided price: the fair probability is an estimate, not a true de-vig."
    : null;
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
