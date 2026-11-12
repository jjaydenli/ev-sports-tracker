import {
  type BoardRow,
  F,
  leagueOf,
  MARKET_ALIASES,
  marketWords,
  str,
  type TeamNames,
  teamNamesFor,
} from "@/lib/board";

/**
 * Lower-case, with accents and apostrophes dropped: "Dončić" → "doncic", "A'ja" → "aja".
 * Applied to both the board's text and what is typed, so either spelling finds the other.
 */
export function fold(text: string): string {
  return text
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .replace(/['’`]/g, "")
    .toLowerCase();
}

/**
 * Where `needle` starts a word of `text`, or -1: "bk" finds "BKN", "angeles" finds
 * "Los Angeles", but "al" does not find "DAL". Both are expected lower-case.
 */
export function startsWord(text: string, needle: string): number {
  for (let at = text.indexOf(needle); at >= 0; at = text.indexOf(needle, at + 1)) {
    if (at === 0 || !/[a-z0-9]/.test(text[at - 1])) return at;
  }
  return -1;
}

/** What a word on the row is: only player and own-team words can anchor an opponent word. */
type Tag = "player" | "team" | "opponent" | "market" | "league";

type Tagged = { word: string; tag: Tag };

/** One row's search words, built once per board load so a keystroke only compares prefixes. */
export type SearchEntry = {
  words: Tagged[];
  /** The market label's parts, for a typed combo: "Pts + Reb" → ["pts", "reb"]. */
  combo: string[];
};

/** Board text as index words. "-" stays inside a word: `startsWord` still finds "double". */
function words(text: string | null): string[] {
  return text === null ? [] : fold(text).split(/[\s+]+/).filter(Boolean);
}

/**
 * The other side of the row's `AWAY@HOME` game; none when there is no game, no "@", or the
 * row's team is on neither side (the same fallback `matchup` uses).
 */
function opponentOf(row: BoardRow): string | null {
  const team = str(row, F.team);
  const sides = (str(row, F.game) ?? "").split("@").map((side) => side.trim());
  if (team === null || sides.length !== 2) return null;
  if (sides[0] === team) return sides[1];
  if (sides[1] === team) return sides[0];
  return null;
}

/** A team code and its full names in the row's league: "DAL Dallas Mavericks". */
function teamText(row: BoardRow, names: TeamNames, code: string | null): string | null {
  return code === null ? null : [code, ...teamNamesFor(names, row, code)].join(" ");
}

export function searchEntry(row: BoardRow, names: TeamNames): SearchEntry {
  const market = str(row, F.market);
  const label = marketWords(market);
  const aliases = Object.keys(MARKET_ALIASES).filter((alias) => MARKET_ALIASES[alias] === market);
  const parts: [Tag, string | null][] = [
    ["player", str(row, F.player)],
    ["team", teamText(row, names, str(row, F.team))],
    ["opponent", teamText(row, names, opponentOf(row))],
    ["market", [label, ...aliases].join(" ")],
    ["league", leagueOf(row)],
  ];
  return {
    words: parts.flatMap(([tag, text]) => words(text).map((word) => ({ word, tag }))),
    combo: fold(label).split("+").map((part) => part.trim()),
  };
}

/** The typed text, parsed once per change rather than once per row. */
export type Query = {
  /** Each must start a word of the row. */
  words: string[];
  /** Each a typed combo ("pts+reb"), which must be the row's market parts in any order. */
  combos: string[][];
};

/** Typed words that mean nothing: "bkn vs dal" is "bkn dal". Never "at", which starts "atl". */
const FILLERS: ReadonlySet<string> = new Set(["vs"]);

export function parseQuery(text: string): Query {
  const query: Query = { words: [], combos: [] };
  for (const token of fold(text).split(/[\s@]+/)) {
    const parts = token.split("+").filter(Boolean);
    if (parts.length > 1) query.combos.push(parts);
    else if (parts.length === 1 && !FILLERS.has(parts[0])) query.words.push(parts[0]);
  }
  return query;
}

function sameParts(a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && a.every((part) => b.includes(part));
}

/**
 * How a row matches every typed word, in any order, or null. A word that matches only the
 * opponent counts only beside a word that matches the player or own team: "dal" is DAL's
 * players, and "kyrie bkn" is Kyrie against BKN. Market and league words narrow but never
 * anchor. "opponent" means some word matched only the opponent; "own" means none did.
 */
export function matchKind(entry: SearchEntry, query: Query): "own" | "opponent" | null {
  if (!query.combos.every((combo) => sameParts(combo, entry.combo))) return null;
  let anchored = false;
  let needsAnchor = false;
  for (const typed of query.words) {
    const tags = new Set(
      entry.words.filter(({ word }) => startsWord(word, typed) >= 0).map(({ tag }) => tag),
    );
    if (!tags.size) return null;
    if (tags.has("player") || tags.has("team")) anchored = true;
    else if (tags.size === 1 && tags.has("opponent")) needsAnchor = true;
  }
  if (needsAnchor && !anchored) return null;
  return needsAnchor ? "opponent" : "own";
}

/**
 * The items matching the query. Opponent matches are a fallback: when any item matches
 * without one, only those are kept. "kyr bkn" is then BKN's Kyrie when there is one, and
 * the Kyrie playing BKN only when there is not. "bkn dal" has no such item (no team is
 * both), so it keeps the whole game.
 */
export function searchHits<T>(
  items: readonly T[],
  entryOf: (item: T) => SearchEntry,
  query: Query,
): T[] {
  const kinds = items.map((item) => matchKind(entryOf(item), query));
  const kept = kinds.includes("own") ? "own" : "opponent";
  return items.filter((_, i) => kinds[i] === kept);
}
