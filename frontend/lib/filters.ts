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
import { startsWord } from "@/lib/search";

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

/** The +EV only and game state toggles: the filters outside the popup and the search box. */
function passesToggles(row: BoardRow, f: Filters): boolean {
  return (
    (!f.plusEvOnly || bool(row, F.plusEv)) &&
    (f.gameState === "all" || (f.gameState === "live") === bool(row, F.isLive))
  );
}

/** Whether a row passes one popup category's picks (none picked passes every row). */
function passesPicks(row: BoardRow, f: Filters, key: FacetKey): boolean {
  return !f[key].size || FACETS[key].values(row).some((value) => f[key].has(value));
}

/** Whether a row passes every filter but the search text. */
export function passesFilters(row: BoardRow, f: Filters): boolean {
  return passesToggles(row, f) && FACET_KEYS.every((key) => passesPicks(row, f, key));
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

/** Props left under the other picks, or picked so it can be removed; the rest are unlisted. */
export function available(option: MenuOption, picked: ReadonlySet<string>): boolean {
  return option.count > 0 || picked.has(option.value);
}

/**
 * Whether a popup search matches an option: every typed word is a piece of its name (or team and
 * game names) or starts a word of its league, so `nba` finds NBA's options but not WNBA's.
 */
export function popupMatches(option: MenuOption, query: string): boolean {
  const league = option.league.toLowerCase();
  return query
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((word) => option.search.includes(word) || startsWord(league, word) >= 0);
}

/** Every popup category's choices, and what its "All …" row counts. */
export type FilterMenus = {
  /** One choice per distinct value on the board, leagues in LEAGUE_ORDER. */
  options: Record<FacetKey, MenuOption[]>;
  /** The props left with the category's own picks taken off. */
  all: Record<FacetKey, number>;
};

/**
 * The popup's choices and counts, in one pass over the rows. A category counts the rows that
 * pass every filter but its own picks; the search text applies only on the board.
 */
export function filterMenus(rows: BoardRow[], filters: Filters, names: TeamNames): FilterMenus {
  const byValue = Object.fromEntries(
    FACET_KEYS.map((key) => [key, new Map<string, MenuOption>()]),
  ) as Record<FacetKey, Map<string, MenuOption>>;
  const all = Object.fromEntries(FACET_KEYS.map((key) => [key, 0])) as Record<FacetKey, number>;
  for (const row of rows) {
    const toggles = passesToggles(row, filters);
    const failed = FACET_KEYS.filter((key) => !passesPicks(row, filters, key));
    for (const key of FACET_KEYS) {
      // Counts toward k when nothing fails, or k's own picks are all that fail.
      const counts = toggles && (!failed.length || (failed.length === 1 && failed[0] === key));
      if (counts) all[key] += 1;
      const facet = FACETS[key];
      for (const value of facet.values(row)) {
        let option = byValue[key].get(value);
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
          byValue[key].set(value, option);
        }
        if (facet.showsLive && bool(row, F.isLive)) option.live = true;
        if (counts) option.count += 1;
      }
    }
  }
  const options = Object.fromEntries(
    FACET_KEYS.map((key) => [
      key,
      [...byValue[key].values()].sort(
        (a, b) =>
          orderRank(LEAGUE_ORDER, a.league) - orderRank(LEAGUE_ORDER, b.league) ||
          a.league.localeCompare(b.league) ||
          a.rank - b.rank ||
          a.name.localeCompare(b.name),
      ),
    ]),
  ) as Record<FacetKey, MenuOption[]>;
  return { options, all };
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
