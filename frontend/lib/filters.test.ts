import { describe, expect, it } from "vitest";

import { type BoardRow, F } from "@/lib/board";
import { type FacetKey, type Filters, filterMenus, NO_FILTERS } from "@/lib/filters";

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
