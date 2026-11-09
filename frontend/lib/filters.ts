import {
  type BoardRow,
  bool,
  F,
  LEAGUE_ORDER,
  leagueOf,
  MARKET_ORDER,
  marketWords,
  matchup,
  matchupNames,
  orderRank,
  str,
  type TeamNames,
  teamNamesFor,
} from "@/lib/board";

export type GameState = "all" | "pre" | "live";

/** The filters picked from a menu; each holds several picks, and none picked means no filter. */
export type FacetKey = "league" | "market" | "game";

export type Filters = {
  plusEvOnly: boolean;
  gameState: GameState;
  player: string;
} & Record<FacetKey, ReadonlySet<string>>;

export const NONE: ReadonlySet<string> = new Set();

export const NO_FILTERS: Filters = {
  plusEvOnly: false,
  league: NONE,
  gameState: "all",
  market: NONE,
  game: NONE,
  player: "",
};

export type Facet = {
  /** The menu button with nothing picked, and the phone sheet's title. */
  title: string;
  /** "2 markets", "Showing all markets", "No market matches …". */
  one: string;
  /** The search box's placeholder; a menu without one has no search. */
  search?: string;
  /** What a pick stores. Market and game carry the league, so NBA Points is not NHL Points. */
  value: (row: BoardRow) => string | null;
  name: (row: BoardRow) => string;
  /** More text the menu's search matches beyond `name`, never shown. */
  alsoSearch?: (row: BoardRow, names: TeamNames) => string;
  /** Order within a league (leagues themselves follow LEAGUE_ORDER); ties go A–Z by name. */
  rank: (row: BoardRow) => number;
  /** Tag in-progress options LIVE. */
  showsLive?: boolean;
};

export const FACETS: Record<FacetKey, Facet> = {
  league: {
    title: "Leagues",
    one: "league",
    value: (row) => leagueOf(row) || null,
    name: leagueOf,
    rank: () => 0,
  },
  market: {
    title: "Markets",
    one: "market",
    search: "Search markets",
    value: (row) => {
      const market = str(row, F.market);
      return market === null ? null : `${leagueOf(row)}|${market}`;
    },
    name: (row) => marketWords(str(row, F.market)),
    rank: (row) => orderRank(MARKET_ORDER[leagueOf(row)], str(row, F.market) ?? ""),
  },
  game: {
    title: "Games",
    one: "game",
    search: "Search games",
    value: (row) => {
      const game = str(row, F.game);
      return game === null ? null : `${leagueOf(row)}|${game}`;
    },
    name: (row) => matchup(row).map((part) => part.text).join(""),
    alsoSearch: matchupNames,
    rank: () => 0,
    showsLive: true,
  },
};

export const FACET_KEYS = Object.keys(FACETS) as FacetKey[];

/** Whether a row passes every filter, or every one but `skip` (a menu's own counts). */
export function matches(row: BoardRow, f: Filters, names: TeamNames, skip?: FacetKey): boolean {
  const query = f.player.trim().toLowerCase();
  const hit = (text: string | null) => (text ?? "").toLowerCase().includes(query);
  return (
    (!f.plusEvOnly || bool(row, F.plusEv)) &&
    (f.gameState === "all" || (f.gameState === "live") === bool(row, F.isLive)) &&
    (!query ||
      hit(str(row, F.player)) ||
      teamNamesFor(names, row, str(row, F.team)).some(hit)) &&
    FACET_KEYS.every(
      (key) => key === skip || !f[key].size || f[key].has(FACETS[key].value(row) ?? ""),
    )
  );
}

/** One choice in a filter menu. `count` honours every other active filter. */
export type MenuOption = {
  value: string;
  league: string;
  name: string;
  /** Lower-case text the menu's search box matches: `name` plus the facet's `alsoSearch`. */
  search: string;
  rank: number;
  live: boolean;
  count: number;
};

/** A menu's choices: one per distinct value on the board, leagues in LEAGUE_ORDER. */
export function menuOptions(
  rows: BoardRow[],
  key: FacetKey,
  filters: Filters,
  names: TeamNames,
): MenuOption[] {
  const facet = FACETS[key];
  const byValue = new Map<string, MenuOption>();
  for (const row of rows) {
    const value = facet.value(row);
    if (value === null) continue;
    let option = byValue.get(value);
    if (!option) {
      const name = facet.name(row);
      option = {
        value,
        league: leagueOf(row),
        name,
        search: `${name} ${facet.alsoSearch?.(row, names) ?? ""}`.toLowerCase(),
        rank: facet.rank(row),
        live: false,
        count: 0,
      };
      byValue.set(value, option);
    }
    if (facet.showsLive && bool(row, F.isLive)) option.live = true;
    if (matches(row, filters, names, key)) option.count += 1;
  }
  return [...byValue.values()].sort(
    (a, b) =>
      orderRank(LEAGUE_ORDER, a.league) - orderRank(LEAGUE_ORDER, b.league) ||
      a.league.localeCompare(b.league) ||
      a.rank - b.rank ||
      a.name.localeCompare(b.name),
  );
}

export function isFiltered(f: Filters): boolean {
  return (
    f.plusEvOnly ||
    f.gameState !== NO_FILTERS.gameState ||
    f.player !== NO_FILTERS.player ||
    FACET_KEYS.some((key) => f[key].size > 0)
  );
}

/** "22 live · 345 pre-game · 0 +EV", counted over the rows that match. */
export function breakdown(props: readonly { row: BoardRow }[]): string {
  let live = 0;
  let plusEv = 0;
  for (const { row } of props) {
    if (bool(row, F.isLive)) live += 1;
    if (bool(row, F.plusEv)) plusEv += 1;
  }
  return `${live} live · ${props.length - live} pre-game · ${plusEv} +EV`;
}

/** "Markets" with nothing picked, "Points" (or "NBA Points" on a multi-league board), "2 markets". */
export function menuLabel(facet: Facet, picked: MenuOption[], prefixLeague: boolean): string {
  if (!picked.length) return facet.title;
  if (picked.length > 1) return `${picked.length} ${facet.one}s`;
  const [only] = picked;
  return prefixLeague ? `${only.league} ${only.name}` : only.name;
}
