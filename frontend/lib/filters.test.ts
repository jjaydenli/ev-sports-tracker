import { describe, expect, it } from "vitest";

import { type BoardRow, F } from "@/lib/board";
import {
  available,
  type FacetKey,
  type Filters,
  filterMenus,
  NO_FILTERS,
  popupMatches,
} from "@/lib/filters";

function row(league: string, game: string, team: string, market: string): BoardRow {
  return { [F.league]: league, [F.game]: game, [F.team]: team, [F.market]: market };
}

const ROWS = [
  row("NBA", "LAL@BOS", "LAL", "points"),
  row("NBA", "LAL@BOS", "BOS", "points"),
  row("NBA", "LAL@BOS", "LAL", "rebounds"),
  // Fails both picks below (league and market), so it counts toward no option.
  row("NHL", "TOR@MTL", "TOR", "points"),
  row("NBA", "DAL@BKN", "DAL", "points"),
];

const PICKS: Filters = {
  ...NO_FILTERS,
  league: new Set(["NBA"]),
  market: new Set(["NBA|points"]),
};

describe("filterMenus counts", () => {
  // A row counts toward category k exactly when the only checks it fails are k's own picks.
  // Expected counts are hand-counted from ROWS and PICKS, not taken from a run.
  it.each<[FacetKey, Record<string, number>]>([
    // League pick skipped, market pick applies: the three NBA points rows.
    ["league", { NBA: 3, NHL: 0 }],
    // Market pick skipped, league pick applies: rebounds counts though it fails the market pick.
    ["market", { "NBA|points": 3, "NBA|rebounds": 1, "NHL|points": 0 }],
    ["team", { "NBA|LAL": 1, "NBA|BOS": 1, "NBA|DAL": 1, "NHL|TOR": 0 }],
    ["game", { "NBA|LAL@BOS": 2, "NBA|DAL@BKN": 1, "NHL|TOR@MTL": 0 }],
  ])("%s", (key, expected) => {
    const counts = Object.fromEntries(
      filterMenus(ROWS, PICKS, {}).options[key].map((option) => [option.value, option.count]),
    );
    expect(counts).toEqual(expected);
  });
});

describe("available", () => {
  it("lists an option with props left, or a picked one, and no other", () => {
    // DAL@BKN has only points. Rebounds is picked first, so it stays removable at 0.
    const picks: Filters = {
      ...NO_FILTERS,
      game: new Set(["NBA|DAL@BKN"]),
      market: new Set(["NBA|rebounds"]),
    };
    const listed = Object.fromEntries(
      filterMenus(ROWS, picks, {}).options.market.map((o) => [
        o.value,
        [o.count, available(o, picks.market)],
      ]),
    );
    expect(listed).toEqual({
      "NBA|points": [1, true],
      "NBA|rebounds": [0, true],
      "NHL|points": [0, false],
    });
  });
});

describe("popupMatches", () => {
  const options = filterMenus(
    [
      ...ROWS,
      row("WNBA", "DAL@LVA", "DAL", "points"),
      row("NBA", "LAL@BOS", "LAL", "pts+reb"),
    ],
    NO_FILTERS,
    {},
  ).options;
  const found = (key: FacetKey, query: string) =>
    options[key].filter((o) => popupMatches(o, query)).map((o) => o.value);

  it("reads a league word as a word start: nba is NBA, never WNBA", () => {
    // Hand-derived from the rows above: NBA has points and Pts + Reb, WNBA has points.
    expect(found("market", "nba").sort()).toEqual(
      ["NBA|points", "NBA|pts+reb", "NBA|rebounds"].sort(),
    );
    expect(found("market", "wnba")).toEqual(["WNBA|points"]);
  });

  it("needs every word: a league word and a name piece together", () => {
    expect(found("market", "nba poin")).toEqual(["NBA|points"]);
    expect(found("team", "wnba dal")).toEqual(["WNBA|DAL"]);
  });

  it("matches nothing for a word that is neither", () => {
    expect(found("market", "nba zzz")).toEqual([]);
  });
});
