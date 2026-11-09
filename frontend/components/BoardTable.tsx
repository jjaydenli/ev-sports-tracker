"use client";

import {
  Fragment,
  type KeyboardEvent,
  type ReactNode,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";

import { TipLayer } from "@/components/Tip";

import {
  BETR,
  type Book,
  type BoardRow,
  DASH,
  F,
  PRICED_BOOKS,
  bool,
  bookPrices,
  edgePts,
  edgeStep,
  formatOdds,
  formatPct,
  formatSignedPct,
  hasPrices,
  LEAGUE_ORDER,
  lineSourceWords,
  MARKET_ORDER,
  marketWords,
  matchup,
  num,
  oneSidedCaveat,
  orderRank,
  pctToAmerican,
  pickLine,
  type Prices,
  str,
  vigWords,
  whySentence,
} from "@/lib/board";

/** A board row with a stable id (its index on the board), so sorting cannot reuse keys. */
type Prop = { id: number; row: BoardRow };

type SortKey = "player" | "hit";

type Sort = { key: SortKey; dir: 1 | -1 };

type Column = {
  id: string;
  header: ReactNode;
  /** Set on a sortable column; its header becomes a sort button. */
  sortKey?: SortKey;
  className?: string;
  /** A per-row class on the cell, added to `className` (the Hit % fill step). */
  cellClass?: (row: BoardRow) => string | null;
  cell: (row: BoardRow) => ReactNode;
};

type GameState = "all" | "pre" | "live";

/** The filters picked from a menu; each holds several picks, and none picked means no filter. */
type FacetKey = "league" | "market" | "game";

type Filters = {
  plusEvOnly: boolean;
  gameState: GameState;
  player: string;
} & Record<FacetKey, ReadonlySet<string>>;

const NONE: ReadonlySet<string> = new Set();

const NO_FILTERS: Filters = {
  plusEvOnly: false,
  league: NONE,
  gameState: "all",
  market: NONE,
  game: NONE,
  player: "",
};

type Facet = {
  /** The menu button with nothing picked, and the phone sheet's title. */
  title: string;
  /** "2 markets", "Showing all markets", "No market matches …". */
  one: string;
  /** The search box's placeholder; a menu without one has no search. */
  search?: string;
  /** What a pick stores. Market and game carry the league, so NBA Points is not NHL Points. */
  value: (row: BoardRow) => string | null;
  name: (row: BoardRow) => string;
  /** Order within a league (leagues themselves follow LEAGUE_ORDER); ties go A–Z by name. */
  rank: (row: BoardRow) => number;
  /** Tag in-progress options LIVE. */
  showsLive?: boolean;
};

const leagueOf = (row: BoardRow) => str(row, F.league) ?? "";

const FACETS: Record<FacetKey, Facet> = {
  league: {
    title: "Leagues",
    one: "league",
    value: (row) => str(row, F.league),
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
    rank: () => 0,
    showsLive: true,
  },
};

const FACET_KEYS = Object.keys(FACETS) as FacetKey[];

const DEFAULT_SORT: Sort = { key: "hit", dir: -1 };

/**
 * Rows shown at first, and added by each "Show more". Growing one list instead of numbered
 * pages keeps every earlier match on screen; filters and sort still cover the whole board.
 */
const PAGE_SIZE = 50;

/** Whether a row passes every filter, or every one but `skip` (a menu's own counts). */
function matches(row: BoardRow, f: Filters, skip?: FacetKey): boolean {
  const query = f.player.trim().toLowerCase();
  return (
    (!f.plusEvOnly || bool(row, F.plusEv)) &&
    (f.gameState === "all" || (f.gameState === "live") === bool(row, F.isLive)) &&
    (!query || (str(row, F.player) ?? "").toLowerCase().includes(query)) &&
    FACET_KEYS.every(
      (key) => key === skip || !f[key].size || f[key].has(FACETS[key].value(row) ?? ""),
    )
  );
}

/** Hit % sorts on EV: the same order as the edge, which is what the colour shows. */
const SORT_VALUE: Record<SortKey, (row: BoardRow) => string | number | null> = {
  player: (row) => str(row, F.player),
  hit: (row) => num(row, F.evPct),
};

/** Sort a copy; rows missing the value go last in either direction. */
function sorted(props: Prop[], { key, dir }: Sort): Prop[] {
  const value = SORT_VALUE[key];
  return [...props].sort((a, b) => {
    const x = value(a.row);
    const y = value(b.row);
    if (x === null) return y === null ? 0 : 1;
    if (y === null) return -1;
    const order =
      typeof x === "string" && typeof y === "string"
        ? x.localeCompare(y)
        : x < y
          ? -1
          : x > y
            ? 1
            : 0;
    return order * dir;
  });
}

/** One choice in a filter menu. `count` honours every other active filter. */
type MenuOption = {
  value: string;
  league: string;
  name: string;
  rank: number;
  live: boolean;
  count: number;
};

/** A menu's choices: one per distinct value on the board, leagues in LEAGUE_ORDER. */
function menuOptions(rows: BoardRow[], key: FacetKey, filters: Filters): MenuOption[] {
  const facet = FACETS[key];
  const byValue = new Map<string, MenuOption>();
  for (const row of rows) {
    const value = facet.value(row);
    if (value === null) continue;
    let option = byValue.get(value);
    if (!option) {
      option = {
        value,
        league: leagueOf(row),
        name: facet.name(row),
        rank: facet.rank(row),
        live: false,
        count: 0,
      };
      byValue.set(value, option);
    }
    if (facet.showsLive && bool(row, F.isLive)) option.live = true;
    if (matches(row, filters, key)) option.count += 1;
  }
  return [...byValue.values()].sort(
    (a, b) =>
      orderRank(LEAGUE_ORDER, a.league) - orderRank(LEAGUE_ORDER, b.league) ||
      a.league.localeCompare(b.league) ||
      a.rank - b.rank ||
      a.name.localeCompare(b.name),
  );
}

function Logo({ book }: { book: Book }) {
  return (
    <span className="logo" tabIndex={0} data-tip={book.name} data-tip-named="">
      {book.logo ? (
        <img src={book.logo} alt="" />
      ) : (
        <span className="mono" aria-hidden="true">
          {book.monogram ?? book.name.slice(0, 2)}
        </span>
      )}
      <span className="sr">{book.name}</span>
    </span>
  );
}

function PlayerCell({ row }: { row: BoardRow }) {
  const side = str(row, F.side);
  const breakeven = num(row, F.betrBreakevenPct);
  return (
    <>
      <span className="idrow">
        <span className="player">{str(row, F.player) ?? DASH}</span>
        <span className="bar" aria-hidden="true" />
        <span className="matchup">
          {matchup(row).map((part, i) =>
            part.own ? <b key={i}>{part.text}</b> : <Fragment key={i}>{part.text}</Fragment>,
          )}
        </span>
        {bool(row, F.isLive) && <span className="live">LIVE</span>}
      </span>
      <span className="pickrow">
        <span className={`sl ${side ?? ""}`}>{pickLine(row)}</span>
        <span className="bar" aria-hidden="true" />
        <span className="mk">{marketWords(str(row, F.market))}</span>
        <span className="be" data-tip={`Betr breakeven ${formatPct(breakeven, 2)}`}>
          {formatOdds(pctToAmerican(breakeven))}
        </span>
        <Logo book={BETR} />
      </span>
    </>
  );
}

function HitCell({ row }: { row: BoardRow }) {
  const hit = num(row, F.hitPct);
  const breakeven = num(row, F.betrBreakevenPct);
  const tip =
    hit === null
      ? undefined
      : `Hit ${formatPct(hit, 2)} · breakeven ${formatPct(breakeven, 2)} · fair ${formatOdds(pctToAmerican(hit))}`;
  return (
    <span className="mstack" data-tip={tip}>
      <span className="hit">{formatPct(hit)}</span>
      <span className="evline">{formatSignedPct(num(row, F.evPct))} EV</span>
    </span>
  );
}

/** "+105/-135" with the picked side bold; over always first. A missing side is a dash. */
function OddsPair({ prices, pickOver }: { prices: Prices; pickOver: boolean }) {
  return (
    <>
      <span className={pickOver ? "on" : undefined}>{formatOdds(prices.over)}</span>
      <span className="sep">/</span>
      <span className={pickOver ? undefined : "on"}>{formatOdds(prices.under)}</span>
    </>
  );
}

function BookCell({ row, book }: { row: BoardRow; book: Book }) {
  const prices = bookPrices(row, book);
  if (!hasPrices(prices)) return <span className="none">{DASH}</span>;
  const vig = vigWords(prices);
  const tip =
    `${book.name}: over ${formatOdds(prices.over)}, under ${formatOdds(prices.under)}` +
    (vig === null ? "" : ` · ${vig}`);
  return (
    <span className="slash" data-tip={tip}>
      <OddsPair prices={prices} pickOver={str(row, F.side) === "over"} />
    </span>
  );
}

function Detail({ row }: { row: BoardRow }) {
  const why = whySentence(row);
  const caveat = oneSidedCaveat(row);
  const side = str(row, F.side);
  const books = PRICED_BOOKS.filter((book) => hasPrices(bookPrices(row, book)));
  return (
    <div className="detail-inner">
      <p className="why">
        {why ? (
          <>
            <span className={why.verdict === "+EV" ? "verdict good" : "verdict"}>{why.verdict}</span>
            Fair chance of the {side ?? "pick"} is <b>{why.fair}</b>; Betr needs <b>{why.need}</b>{" "}
            to break even.
          </>
        ) : (
          "Not enough prices to call this one."
        )}
      </p>
      <p className="source">{lineSourceWords(row)}, vig removed</p>
      {books.length > 0 && (
        <ul className="book-prices">
          {books.map((book) => {
            const prices = bookPrices(row, book);
            return (
              <li key={book.key}>
                <span className="bookname">
                  <Logo book={book} />
                  {book.name}
                </span>
                <span className="slash">
                  <OddsPair prices={prices} pickOver={side === "over"} />
                </span>
                <span className="vig">{vigWords(prices) ?? ""}</span>
              </li>
            );
          })}
        </ul>
      )}
      {caveat && <p className="caveat">{caveat}</p>}
    </div>
  );
}

function columnsFor(rows: BoardRow[]): Column[] {
  const shown = PRICED_BOOKS.filter((book) =>
    rows.some((row) => hasPrices(bookPrices(row, book))),
  );
  return [
    {
      id: "player",
      header: "Player",
      sortKey: "player",
      className: "sticky-col",
      cell: (row) => <PlayerCell row={row} />,
    },
    {
      id: "hit",
      header: "Hit %",
      sortKey: "hit",
      className: "metric",
      cellClass: (row) => edgeStep(edgePts(row)),
      cell: (row) => <HitCell row={row} />,
    },
    ...shown.map(
      (book): Column => ({
        id: book.key,
        header: <Logo book={book} />,
        className: "book",
        cell: (row) => <BookCell row={row} book={book} />,
      }),
    ),
  ];
}

const ICON_PROPS = { "aria-hidden": true, focusable: false } as const;

function Chevron({ className }: { className?: string }) {
  return (
    <svg className={className} width="12" height="12" viewBox="0 0 12 12" {...ICON_PROPS}>
      <path
        d="M3 4.5 6 7.5 9 4.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function Magnifier() {
  return (
    <svg className="mag" width="16" height="16" viewBox="0 0 16 16" {...ICON_PROPS}>
      <circle cx="7" cy="7" r="4.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <path d="M10.5 10.5 14 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function Tick() {
  return (
    <span className="tick">
      <svg width="12" height="12" viewBox="0 0 12 12" {...ICON_PROPS}>
        <path
          d="M2.5 6.2 5 8.5 9.5 3.5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </span>
  );
}

/** "Markets" with nothing picked, "Points" (or "NBA Points" on a multi-league board), "2 markets". */
function menuLabel(facet: Facet, picked: MenuOption[], prefixLeague: boolean): string {
  if (!picked.length) return facet.title;
  if (picked.length > 1) return `${picked.length} ${facet.one}s`;
  const [only] = picked;
  return prefixLeague ? `${only.league} ${only.name}` : only.name;
}

/**
 * One filter's dropdown: pick several, each with its count under the other filters. On a board
 * with two or more leagues, Market and Game group their choices under a foldable heading per
 * league; the first open folds every league except one holding a pick, and folds then persist.
 */
function FilterMenu({
  facetKey,
  options,
  picked,
  leagues,
  multiLeague,
  onChange,
}: {
  facetKey: FacetKey;
  options: MenuOption[];
  picked: ReadonlySet<string>;
  /** The League filter's picks; Market and Game then list only those leagues. */
  leagues: ReadonlySet<string>;
  multiLeague: boolean;
  onChange: (next: ReadonlySet<string>) => void;
}) {
  const facet = FACETS[facetKey];
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  /** Folded leagues; null until the first open decides them. */
  const [folded, setFolded] = useState<ReadonlySet<string> | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const popId = useId();

  const focusList = () =>
    (searchRef.current ?? listRef.current?.querySelector<HTMLElement>(".opt"))?.focus();

  const close = (refocus: boolean) => {
    setOpen(false);
    if (refocus) triggerRef.current?.focus();
  };

  // Outside click closes; Esc closes and returns focus to the button.
  useEffect(() => {
    if (!open) return;
    focusList();
    const onDown = (event: MouseEvent) => {
      if (!wrapRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      triggerRef.current?.focus();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const toggleOpen = () => {
    if (open) return close(false);
    if (folded === null) {
      const holdingPick = new Set(options.filter((o) => picked.has(o.value)).map((o) => o.league));
      setFolded(new Set(options.map((o) => o.league).filter((lg) => !holdingPick.has(lg))));
    }
    setQuery("");
    setOpen(true);
  };

  const toggle = (value: string) => {
    const next = new Set(picked);
    if (!next.delete(value)) next.add(value);
    onChange(next);
  };

  const toggleFold = (lg: string) =>
    setFolded((current) => {
      const next = new Set(current);
      if (!next.delete(lg)) next.add(lg);
      return next;
    });

  // Arrow keys step through options and league headings; Enter and Space toggle (they are buttons).
  const onListKey = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    event.preventDefault();
    const items = [...(listRef.current?.querySelectorAll<HTMLElement>(".opt, .lhead") ?? [])];
    const at = items.indexOf(document.activeElement as HTMLElement);
    const step = event.key === "ArrowDown" ? 1 : -1;
    items[Math.max(0, Math.min(items.length - 1, at + step))]?.focus();
  };

  const needle = query.trim().toLowerCase();
  const shown = options.filter(
    (o) =>
      (!needle || o.name.toLowerCase().includes(needle)) &&
      (facetKey === "league" || !leagues.size || leagues.has(o.league)),
  );
  const sectionLeagues = [...new Set(shown.map((o) => o.league))];
  const sectioned = facetKey !== "league" && sectionLeagues.length > 1;
  const pickedOptions = options.filter((o) => picked.has(o.value));

  const optionButton = (o: MenuOption, tagged: boolean) => (
    <button
      key={o.value}
      type="button"
      className={tagged ? "opt" : "opt notag"}
      aria-pressed={picked.has(o.value)}
      onClick={() => toggle(o.value)}
    >
      {tagged && <span className="tag">{o.league}</span>}
      <span className="nm">
        {o.name}
        {o.live && <span className="live">LIVE</span>}
      </span>
      <span className="n">{o.count}</span>
      <Tick />
    </button>
  );

  return (
    <div className="dd" ref={wrapRef}>
      <button
        ref={triggerRef}
        type="button"
        className={picked.size ? "trig set" : "trig"}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={open ? popId : undefined}
        onClick={toggleOpen}
      >
        <span className="tl">{menuLabel(facet, pickedOptions, multiLeague && facetKey !== "league")}</span>
        <Chevron />
      </button>
      {open && (
        <>
          <div className="scrim" onClick={() => close(true)} />
          <div className="pop" id={popId} role="dialog" aria-label={facet.title}>
            <div className="phead">
              <h3>{facet.title}</h3>
              <button type="button" className="xbtn" aria-label="Close" onClick={() => close(true)}>
                ×
              </button>
            </div>
            {facet.search && (
              <div className="lsearch">
                <Magnifier />
                <input
                  ref={searchRef}
                  type="search"
                  placeholder={facet.search}
                  aria-label={facet.search}
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                />
              </div>
            )}
            {/* Always present, so the list never shifts on the first pick; Clear is held invisible. */}
            <div className="pickline">
              <span>{picked.size ? `${picked.size} picked` : `Showing all ${facet.one}s`}</span>
              <button
                type="button"
                className={picked.size ? "link clr" : "link clr idle"}
                aria-hidden={!picked.size}
                tabIndex={picked.size ? undefined : -1}
                onClick={() => {
                  onChange(NONE);
                  focusList();
                }}
              >
                Clear
              </button>
            </div>
            <div
              className="opts"
              ref={listRef}
              role="group"
              aria-label={facet.title}
              onKeyDown={onListKey}
            >
              {sectioned
                ? sectionLeagues.map((lg) => {
                    const mine = shown.filter((o) => o.league === lg);
                    const shut = !needle && (folded?.has(lg) ?? false);
                    const pickedHere = mine.filter((o) => picked.has(o.value)).length;
                    return (
                      <Fragment key={lg}>
                        <button
                          type="button"
                          className="lhead"
                          aria-expanded={!shut}
                          onClick={() => toggleFold(lg)}
                        >
                          <Chevron className="fold" />
                          <span>{lg}</span>
                          <span className="lsum">
                            {pickedHere ? `${pickedHere} picked · ` : ""}
                            {mine.length}
                          </span>
                        </button>
                        {!shut && mine.map((o) => optionButton(o, false))}
                      </Fragment>
                    );
                  })
                : shown.map((o) => optionButton(o, facetKey !== "league"))}
              {!shown.length && (
                <p className="nomatch">
                  No {facet.one} matches “{query.trim()}”.
                </p>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

const GAME_STATES: { value: GameState; label: string }[] = [
  { value: "all", label: "All" },
  { value: "pre", label: "Pre-game" },
  { value: "live", label: "Live" },
];

function isFiltered(f: Filters): boolean {
  return (
    f.plusEvOnly ||
    f.gameState !== NO_FILTERS.gameState ||
    f.player !== NO_FILTERS.player ||
    FACET_KEYS.some((key) => f[key].size > 0)
  );
}

/** "22 live · 345 pre-game · 0 +EV", counted over the rows that match. */
function breakdown(props: Prop[]): string {
  let live = 0;
  let plusEv = 0;
  for (const { row } of props) {
    if (bool(row, F.isLive)) live += 1;
    if (bool(row, F.plusEv)) plusEv += 1;
  }
  return `${live} live · ${props.length - live} pre-game · ${plusEv} +EV`;
}

function FilterBar({
  rows,
  filters,
  onChange,
  count,
}: {
  rows: BoardRow[];
  filters: Filters;
  onChange: (change: Partial<Filters>) => void;
  count: string;
}) {
  const options = Object.fromEntries(
    FACET_KEYS.map((key) => [key, menuOptions(rows, key, filters)]),
  ) as Record<FacetKey, MenuOption[]>;
  const menu = (key: FacetKey) => (
    <FilterMenu
      facetKey={key}
      options={options[key]}
      picked={filters[key]}
      leagues={filters.league}
      multiLeague={options.league.length > 1}
      onChange={(next) => onChange({ [key]: next })}
    />
  );
  return (
    <div className="filters" role="group" aria-label="Filters">
      <button
        type="button"
        className="evt"
        aria-pressed={filters.plusEvOnly}
        onClick={() => onChange({ plusEvOnly: !filters.plusEvOnly })}
      >
        +EV only
      </button>
      {menu("league")}
      <div className="seg" role="group" aria-label="Game state">
        {GAME_STATES.map(({ value, label }) => (
          <button
            key={value}
            type="button"
            aria-pressed={filters.gameState === value}
            onClick={() => onChange({ gameState: value })}
          >
            {label}
          </button>
        ))}
      </div>
      {menu("market")}
      {menu("game")}
      <span className="searchwrap">
        <Magnifier />
        <input
          type="search"
          className={filters.player ? "set" : undefined}
          placeholder="Search player"
          aria-label="Search player"
          value={filters.player}
          onChange={(event) => onChange({ player: event.target.value })}
        />
      </span>
      {/* Always rendered, so its space is held and the table does not jump when it shows. */}
      <button
        type="button"
        className={isFiltered(filters) ? "clear" : "clear idle"}
        aria-hidden={!isFiltered(filters)}
        tabIndex={isFiltered(filters) ? undefined : -1}
        onClick={() => onChange(NO_FILTERS)}
      >
        Clear filters
      </button>
      <span className="count" aria-live="polite">
        {count}
      </span>
    </div>
  );
}

function SortHeader({
  col,
  sortKey,
  sort,
  onSort,
}: {
  col: Column;
  sortKey: SortKey;
  sort: Sort;
  onSort: (key: SortKey) => void;
}) {
  const active = sort.key === sortKey;
  const dir = sort.dir < 0 ? "descending" : "ascending";
  return (
    <th scope="col" className={col.className} aria-sort={active ? dir : undefined}>
      <button type="button" className="sort" onClick={() => onSort(sortKey)}>
        {col.header}
        <span className="arrow" aria-hidden="true">
          {active ? (sort.dir < 0 ? "▾" : "▴") : ""}
        </span>
      </button>
    </th>
  );
}

export function BoardTable({ rows }: { rows: BoardRow[] }) {
  const [open, setOpen] = useState<number | null>(null);
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [sort, setSort] = useState<Sort>(DEFAULT_SORT);
  const [shownCount, setShownCount] = useState(PAGE_SIZE);
  /** Position of the first row a "Show more" added, to bring into view once it renders. */
  const [revealFrom, setRevealFrom] = useState<number | null>(null);
  const gridRef = useRef<HTMLDivElement>(null);

  const columns = useMemo(() => columnsFor(rows), [rows]);
  const props = useMemo(() => rows.map((row, id): Prop => ({ id, row })), [rows]);
  const matching = useMemo(
    () => sorted(props.filter(({ row }) => matches(row, filters)), sort),
    [props, filters, sort],
  );

  // Scroll the table so the first added row sits one row below the top, keeping the last
  // row already read in sight. Focus stays on the button that was pressed.
  useEffect(() => {
    const grid = gridRef.current;
    if (revealFrom === null || !grid) return;
    setRevealFrom(null);
    const first = grid.querySelector<HTMLElement>(`tr.prop[data-pos="${revealFrom}"]`);
    const head = grid.querySelector("thead");
    if (!first || !head) return;
    const lastRead = first.previousElementSibling as HTMLElement | null;
    const offset =
      first.getBoundingClientRect().top -
      grid.getBoundingClientRect().top -
      head.getBoundingClientRect().height -
      (lastRead?.getBoundingClientRect().height ?? 0);
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    grid.scrollBy({ top: offset, behavior: still ? "auto" : "smooth" });
    // "Show all" and the last "Show more" remove the button that held focus.
    if (!grid.contains(document.activeElement)) first.focus({ preventScroll: true });
  }, [revealFrom]);

  if (!rows.length) {
    return <p className="empty">No props on the board.</p>;
  }

  // Any filter or sort change goes back to the first page.
  const changeFilters = (change: Partial<Filters>) => {
    setFilters((current) => ({ ...current, ...change }));
    setShownCount(PAGE_SIZE);
  };
  const changeSort = (key: SortKey) => {
    setSort((current) =>
      current.key === key
        ? { key, dir: current.dir === 1 ? -1 : 1 }
        : { key, dir: key === "player" ? 1 : -1 },
    );
    setShownCount(PAGE_SIZE);
  };

  const visible = matching.slice(0, shownCount);
  const remaining = matching.length - visible.length;
  const showTo = (count: number) => {
    setRevealFrom(visible.length);
    setShownCount(count);
  };

  return (
    <>
      <FilterBar
        rows={rows}
        filters={filters}
        onChange={changeFilters}
        count={breakdown(matching)}
      />
      <div className="grid" ref={gridRef}>
        <table className="board">
          <thead>
            <tr>
              {columns.map((col) =>
                col.sortKey ? (
                  <SortHeader
                    key={col.id}
                    col={col}
                    sortKey={col.sortKey}
                    sort={sort}
                    onSort={changeSort}
                  />
                ) : (
                  <th key={col.id} scope="col" className={col.className}>
                    {col.header}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="empty">
                  No props match these filters.
                </td>
              </tr>
            )}
            {visible.map(({ id, row }, pos) => {
              const isOpen = open === id;
              const toggle = () => setOpen(isOpen ? null : id);
              return (
                <Fragment key={id}>
                  <tr
                    className={pos % 2 ? "prop alt" : "prop"}
                    data-pos={pos}
                    tabIndex={0}
                    aria-expanded={isOpen}
                    onClick={(event) => {
                      if ((event.target as Element).closest(".logo")) return;
                      toggle();
                    }}
                    onKeyDown={(event) => {
                      if (event.target !== event.currentTarget) return;
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        toggle();
                      }
                    }}
                  >
                    {columns.map((col) => (
                      <td
                        key={col.id}
                        className={
                          [col.className, col.cellClass?.(row)].filter(Boolean).join(" ") ||
                          undefined
                        }
                      >
                        {col.cell(row)}
                      </td>
                    ))}
                  </tr>
                  {isOpen && (
                    <tr className="detail">
                      <td colSpan={columns.length}>
                        <Detail row={row} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
            {matching.length > PAGE_SIZE && (
              <tr className="more-row">
                <td colSpan={columns.length}>
                  <div className="more-inner">
                    <span className="progress" aria-live="polite">
                      {remaining > 0
                        ? `Showing ${visible.length} of ${matching.length}`
                        : `Showing all ${matching.length}`}
                    </span>
                    {remaining > 0 && (
                      <>
                        <button
                          type="button"
                          className="more"
                          onClick={() => showTo(shownCount + PAGE_SIZE)}
                        >
                          Show {Math.min(PAGE_SIZE, remaining)} more
                        </button>
                        <button
                          type="button"
                          className="link"
                          onClick={() => showTo(matching.length)}
                        >
                          Show all
                        </button>
                      </>
                    )}
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <TipLayer />
    </>
  );
}
