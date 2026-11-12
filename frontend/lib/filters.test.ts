import { describe, expect, it } from "vitest";

import { type BoardRow, F, type TeamNames } from "@/lib/board";
import {
  type FacetKey,
  type Filters,
  filterMenus,
  grayed,
  matches,
  NO_FILTERS,
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

describe("grayed", () => {
  it("grays an option with no props left, but never a picked one", () => {
    // DAL@BKN has only points. Rebounds is picked first, so it stays removable at 0.
    const picks: Filters = {
      ...NO_FILTERS,
      game: new Set(["NBA|DAL@BKN"]),
      market: new Set(["NBA|rebounds"]),
    };
    const gray = Object.fromEntries(
      filterMenus(ROWS, picks, {}).options.market.map((o) => [
        o.value,
        [o.count, grayed(o, picks.market)],
      ]),
    );
    expect(gray).toEqual({
      "NBA|points": [1, false],
      "NBA|rebounds": [0, false],
      "NHL|points": [0, true],
    });
  });
});

describe("classic search", () => {
  // The search on main before universal search: the whole query as one word-start prefix of
  // the player, the own team's code or its full name. Deleted with the classic matcher.
  const names: TeamNames = { NBA: { DAL: ["Dallas Mavericks"], LAL: ["Los Angeles Lakers"] } };
  const players: Record<string, BoardRow> = {
    kyrie: { [F.league]: "NBA", [F.game]: "LAL@DAL", [F.team]: "DAL", [F.player]: "Kyrie Irving" },
    luka: { [F.league]: "NBA", [F.game]: "LAL@DAL", [F.team]: "LAL", [F.player]: "Luka Dončić" },
    aja: { [F.league]: "WNBA", [F.game]: "DAL@LV", [F.team]: "LV", [F.player]: "A'ja Wilson" },
  };

  // Expected sets are read off the three rows above by hand.
  it.each<[string, string[]]>([
    ["kyr", ["kyrie"]], // start of the player's first name
    ["irv", ["kyrie"]], // start of a later word
    ["KYRIE irving", ["kyrie"]], // case and the whole name as a phrase
    ["dal", ["kyrie"]], // own team's code, never the opponent's (Luka plays against DAL)
    ["los angeles", ["luka"]], // own team's full name, as a phrase
    ["al", []], // not the start of a word: "DAL" and "Dallas" hold it mid-word
    ["rving", []],
    ["  kyrie   irving ", ["kyrie"]], // spaces trimmed and collapsed
    // Accents and apostrophes are dropped on both sides (Decision 18).
    ["doncic", ["luka"]],
    ["Dončić", ["luka"]],
    ["aja", ["aja"]],
    ["a'ja", ["aja"]],
  ])("%j", (text, expected) => {
    const found = Object.keys(players).filter((id) =>
      matches(players[id], { ...NO_FILTERS, text }, names),
    );
    expect(found).toEqual(expected);
  });
});
