import { describe, expect, it } from "vitest";

import { type BoardRow, F, type TeamNames } from "@/lib/board";
import { type Filters, NO_FILTERS, passesFilters } from "@/lib/filters";
import { matchesQuery, parseQuery, searchEntry } from "@/lib/search";

function row(league: string, game: string, team: string, player: string, market: string) {
  return {
    [F.league]: league,
    [F.game]: game,
    [F.team]: team,
    [F.player]: player,
    [F.market]: market,
  } as BoardRow;
}

const NAMES: TeamNames = {
  NBA: {
    DAL: ["Dallas Mavericks"],
    BKN: ["Brooklyn Nets"],
    PHI: ["Philadelphia 76ers"],
    BOS: ["Boston Celtics"],
  },
  WNBA: { DAL: ["Dallas Wings"], LV: ["Las Vegas Aces"] },
  MLB: { ATL: ["Atlanta Braves"], PHI: ["Philadelphia Phillies"] },
};

/** A small fixed board. Every expected set below is read off this table by hand. */
const ROWS: Record<string, BoardRow> = {
  kyriePts: row("NBA", "BKN@DAL", "DAL", "Kyrie Irving", "points"),
  kyriePr: row("NBA", "BKN@DAL", "DAL", "Kyrie Irving", "pts+reb"),
  kyrieDd: row("NBA", "BKN@DAL", "DAL", "Kyrie Irving", "double-double"),
  lukaReb: row("NBA", "BKN@DAL", "DAL", "Luka Dončić", "rebounds"),
  klayFs: row("NBA", "BKN@DAL", "DAL", "Klay Thompson", "fantasy_pts"),
  camPts: row("NBA", "BKN@DAL", "BKN", "Cam Thomas", "points"),
  camPra: row("NBA", "BKN@DAL", "BKN", "Cam Thomas", "pra"),
  camTd: row("NBA", "BKN@DAL", "BKN", "Cam Thomas", "triple-double"),
  nicRa: row("NBA", "BKN@DAL", "BKN", "Nic Claxton", "reb+ast"),
  maxeyPts: row("NBA", "PHI@BOS", "PHI", "Tyrese Maxey", "points"),
  arikePts: row("WNBA", "DAL@LV", "DAL", "Arike Ogunbowale", "points"),
  ajaPts: row("WNBA", "DAL@LV", "LV", "A'ja Wilson", "points"),
  acunaTb: row("MLB", "ATL@PHI", "ATL", "Ronald Acuña Jr.", "total_bases"),
  harperSb: row("MLB", "ATL@PHI", "PHI", "Bryce Harper", "stolen_bases"),
};

const ENTRIES = Object.fromEntries(
  Object.entries(ROWS).map(([id, r]) => [id, searchEntry(r, NAMES)]),
);

function found(text: string, filters: Filters = NO_FILTERS): string[] {
  const query = parseQuery(text);
  return Object.keys(ROWS).filter(
    (id) => passesFilters(ROWS[id], filters) && matchesQuery(ENTRIES[id], query),
  );
}

const BKN_DAL_GAME = [
  "kyriePts",
  "kyriePr",
  "kyrieDd",
  "lukaReb",
  "klayFs",
  "camPts",
  "camPra",
  "camTd",
  "nicRa",
];

describe("universal search", () => {
  it.each<[string, string[]]>([
    ["", Object.keys(ROWS)],
    // Teams: a word that matches only the opponent needs a player or own-team word beside it.
    ["dal", ["kyriePts", "kyriePr", "kyrieDd", "lukaReb", "klayFs", "arikePts"]],
    ["dallas", ["kyriePts", "kyriePr", "kyrieDd", "lukaReb", "klayFs", "arikePts"]],
    ["bkn dal", BKN_DAL_GAME],
    ["dal bkn", BKN_DAL_GAME],
    ["kyrie bkn", ["kyriePts", "kyriePr", "kyrieDd"]],
    ["dal points", ["kyriePts", "arikePts"]], // market words are not anchors
    // League words narrow, and "nba" does not start "wnba".
    ["dal nba", ["kyriePts", "kyriePr", "kyrieDd", "lukaReb", "klayFs"]],
    ["dal wnba", ["arikePts"]],
    ["phi nba", ["maxeyPts"]],
    // Markets: word-start matching on the labels, no special rule.
    ["points", ["kyriePts", "camPts", "maxeyPts", "arikePts", "ajaPts"]],
    ["pts", ["kyriePr", "camPra"]],
    ["reb", ["kyriePr", "lukaReb", "camPra", "nicRa"]],
    ["pts reb", ["kyriePr", "camPra"]],
    ["pts+reb", ["kyriePr"]], // that exact combo, in either order
    ["reb+pts", ["kyriePr"]],
    ["reboun", ["lukaReb"]],
    ["rebs", []],
    ["bases", ["acunaTb", "harperSb"]],
    ["bases total", ["acunaTb"]],
    ["stolen", ["harperSb"]],
    ["double", ["kyrieDd", "camTd"]],
    // Fillers: "@" splits and "vs" drops; "at" is never one.
    ["bkn@dal", BKN_DAL_GAME],
    ["bkn vs dal", BKN_DAL_GAME],
    ["atl", ["acunaTb"]],
    ["at", ["acunaTb"]],
    // Accents and apostrophes, on both sides.
    ["doncic", ["lukaReb"]],
    ["Dončić", ["lukaReb"]],
    ["acuna", ["acunaTb"]],
    ["aja", ["ajaPts"]],
    ["a'ja", ["ajaPts"]],
    // Case, and spaces around and between words.
    ["  KYRIE   Points ", ["kyriePts"]],
  ])("%j", (text, expected) => {
    expect(found(text)).toEqual(expected);
  });

  it("runs within the picked filters, and a chip never anchors", () => {
    const dalNba: Filters = { ...NO_FILTERS, team: new Set(["NBA|DAL"]) };
    // "bkn" matches only the DAL players' opponent, and the chip is not a word.
    expect(found("bkn", dalNba)).toEqual([]);
    expect(found("kyrie", dalNba)).toEqual(["kyriePts", "kyriePr", "kyrieDd"]);
    // The text contradicts the chip: zero is right.
    expect(found("dal wnba", dalNba)).toEqual([]);
  });
});
