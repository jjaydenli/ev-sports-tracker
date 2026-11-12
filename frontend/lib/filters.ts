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

/** The filters picked in the Filters popup; each holds several picks, and none means no filter. */
export type FacetKey = "league" | "game" | "team" | "market";

export type Filters = {
  plusEvOnly: boolean;
  gameState: GameState;
  /** What was typed in the search box: filters live by player and team, no pick needed. */
  text: string;
} & Record<FacetKey, ReadonlySet<string>>;

export const NONE: ReadonlySet<string> = new Set();

export const NO_FILTERS: Filters = {
  plusEvOnly: false,
  league: NONE,
  gameState: "all",
  market: NONE,
  game: NONE,
  team: NONE,
  text: "",
};

export type Facet = {
  /** The menu button with nothing picked, the phone sheet's title, the search heading. */
  title: string;
  /** "2 markets", "Showing all markets", "No market matches …". */
  one: string;
  /** The search box's placeholder; a menu without one has no search. */
  search?: string;
  /**
   * What a pick stores, and the picks a row passes. Each carries the league, so NBA Points is
   * not NHL Points; none means the row passes no pick.
   */
  values: (row: BoardRow) => string[];
  /** `value` is one of the row's `values` (a row can stand for two teams). */
  name: (row: BoardRow, names: TeamNames, value: string) => string;
  /** More text the search matches beyond `name`, never shown. */
  alsoSearch?: (row: BoardRow, names: TeamNames, value: string) => string;
  /** Order within a league (leagues themselves follow LEAGUE_ORDER); ties go A–Z by name. */
  rank: (row: BoardRow) => number;
  /** Tag in-progress options LIVE. */
  showsLive?: boolean;
};

/** "NBA|LAL" for a row's league and a code or name: the shape every facet's value takes. */
function scoped(row: BoardRow, part: string | null): string[] {
  return part === null ? [] : [`${leagueOf(row)}|${part}`];
}

/** The part of a value after its league: "LAL" from "NBA|LAL". */
export function unscoped(value: string): string {
  return value.slice(value.indexOf("|") + 1);
}

export const FACETS: Record<FacetKey, Facet> = {
  league: {
    title: "Leagues",
    one: "league",
    values: (row) => (leagueOf(row) ? [leagueOf(row)] : []),
    name: leagueOf,
    rank: () => 0,
  },
  game: {
    title: "Games",
    one: "game",
    search: "Search games",
    values: (row) => scoped(row, str(row, F.game)),
    name: (row) => matchup(row).map((part) => part.text).join(""),
    alsoSearch: matchupNames,
    rank: () => 0,
    showsLive: true,
  },
  team: {
    title: "Teams",
    one: "team",
    search: "Search teams",
    // A team pick reaches that team's own players, not their opponents.
    values: (row) => scoped(row, str(row, F.team)),
    // An old API sends no team_names: the code stands in for the name.
    name: (row, names, value) => teamNamesFor(names, row, unscoped(value))[0] ?? unscoped(value),
    alsoSearch: (row, names, value) =>
      [unscoped(value), ...teamNamesFor(names, row, unscoped(value))].join(" "),
    rank: () => 0,
  },
  market: {
    title: "Markets",
    one: "market",
    search: "Search markets",
    values: (row) => scoped(row, str(row, F.market)),
    name: (row) => marketWords(str(row, F.market)),
    rank: (row) => orderRank(MARKET_ORDER[leagueOf(row)], str(row, F.market) ?? ""),
  },
};

export const FACET_KEYS = Object.keys(FACETS) as FacetKey[];

/** The change that empties every popup category: what Clear all does. */
export const NO_PICKS = Object.fromEntries(FACET_KEYS.map((key) => [key, NONE])) as Record<
  FacetKey,
  ReadonlySet<string>
>;

/** How many options are picked across the popup's categories. */
export function pickCount(f: Filters): number {
  return FACET_KEYS.reduce((sum, key) => sum + f[key].size, 0);
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

/** Whether a row passes every filter, or every one but `skip` (a category's own counts). */
export function matches(row: BoardRow, f: Filters, names: TeamNames, skip?: FacetKey): boolean {
  const query = f.text.trim().toLowerCase().replace(/\s+/g, " ");
  const typed = () =>
    [str(row, F.player), str(row, F.team), ...teamNamesFor(names, row, str(row, F.team))].some(
      (text) => startsWord((text ?? "").toLowerCase(), query) >= 0,
    );
  return (
    (!f.plusEvOnly || bool(row, F.plusEv)) &&
    (f.gameState === "all" || (f.gameState === "live") === bool(row, F.isLive)) &&
    (!query || typed()) &&
    FACET_KEYS.every(
      (key) =>
        key === skip ||
        !f[key].size ||
        FACETS[key].values(row).some((value) => f[key].has(value)),
    )
  );
}

/** One choice in a filter menu. `count` honours every other active filter except the text. */
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
  // The popup counts what its own picks leave; the search text applies only on the board.
  const picksOnly = { ...filters, text: "" };
  const byValue = new Map<string, MenuOption>();
  for (const row of rows) {
    const passes = matches(row, picksOnly, names, key);
    for (const value of facet.values(row)) {
      let option = byValue.get(value);
      if (!option) {
        const name = facet.name(row, names, value);
        option = {
          value,
          league: leagueOf(row),
          name,
          search: `${name} ${facet.alsoSearch?.(row, names, value) ?? ""}`.toLowerCase(),
          rank: facet.rank(row),
          live: false,
          count: 0,
        };
        byValue.set(value, option);
      }
      if (facet.showsLive && bool(row, F.isLive)) option.live = true;
      if (passes) option.count += 1;
    }
  }
  return [...byValue.values()].sort(
    (a, b) =>
      orderRank(LEAGUE_ORDER, a.league) - orderRank(LEAGUE_ORDER, b.league) ||
      a.league.localeCompare(b.league) ||
      a.rank - b.rank ||
      a.name.localeCompare(b.name),
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

/** What a pick reads as on its chip: "NBA", "BKN @ DAL", "DAL (NBA)", "Points". */
export function chipLabel(key: FacetKey, option: MenuOption): string {
  return key === "team" ? `${unscoped(option.value)} (${option.league})` : option.name;
}

/**
 * The popup's "everything" row: "All markets", "All markets in NBA, NHL", "All live markets in
 * NBA, NHL", and "All markets in 3 leagues" past two leagues. Games, teams and markets follow
 * the picked leagues, and the game state when it narrows.
 */
export function allLabel(key: FacetKey, f: Filters): string {
  const noun = `${FACETS[key].one}s`;
  const state = f.gameState === "live" ? "live " : f.gameState === "pre" ? "pre-game " : "";
  if (key === "league" || !f.league.size) return `All ${state}${noun}`;
  const leagues = [...f.league].sort(
    (a, b) => orderRank(LEAGUE_ORDER, a) - orderRank(LEAGUE_ORDER, b),
  );
  return leagues.length > 2
    ? `All ${state}${noun} in ${leagues.length} leagues`
    : `All ${state}${noun} in ${leagues.join(", ")}`;
}

export type Chip = {
  id: string;
  label: string;
  /** Hover text where the label alone is ambiguous ("Points" in which league). */
  title?: string;
  /** The change that takes this pick off. */
  remove: Partial<Filters>;
};

function without(set: ReadonlySet<string>, value: string): ReadonlySet<string> {
  const next = new Set(set);
  next.delete(value);
  return next;
}

/**
 * Every popup pick, as a chip. +EV only and the game state get none: their toggles in the bar
 * already show them.
 */
export function activePicks(options: Record<FacetKey, MenuOption[]>, filters: Filters): Chip[] {
  return FACET_KEYS.flatMap((key) =>
    [...filters[key]].map((value): Chip => {
      const option = options[key].find((o) => o.value === value);
      return {
        id: `${key}:${value}`,
        label: option ? chipLabel(key, option) : unscoped(value),
        title: option && key === "market" ? `${option.league} ${option.name}` : undefined,
        remove: { [key]: without(filters[key], value) },
      };
    }),
  );
}
