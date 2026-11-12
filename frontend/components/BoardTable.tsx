"use client";

import {
  Fragment,
  type ReactNode,
  type RefObject,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { ChipRow } from "@/components/ChipRow";
import { FiltersPopup } from "@/components/FiltersPopup";
import { SearchBox } from "@/components/SearchBox";

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
  lineSourceWords,
  marketWords,
  matchup,
  num,
  oneSidedCaveat,
  pctToAmerican,
  pickLine,
  type Prices,
  str,
  type TeamNames,
  vigWords,
  whySentence,
} from "@/lib/board";
import {
  activePicks,
  breakdown,
  FACETS,
  type FacetKey,
  filterMenus,
  type Filters,
  type GameState,
  matches,
  type MenuOption,
  NO_FILTERS,
  NO_PICKS,
  passesFilters,
  pickCount,
} from "@/lib/filters";
import { matchesQuery, parseQuery, type SearchEntry, searchEntry } from "@/lib/search";

/**
 * A board row with a stable id (its index on the board), so sorting cannot reuse keys, and
 * its search words, built once per board load.
 */
type Prop = { id: number; row: BoardRow; search: SearchEntry };

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

const DEFAULT_SORT: Sort = { key: "hit", dir: -1 };

/**
 * Rows shown at first, and added by each "Show more". Growing one list instead of numbered
 * pages keeps every earlier match on screen; filters and sort still cover the whole board.
 */
const PAGE_SIZE = 50;

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

/** "+105/-135" with the picked side bold; over always first. A missing side is a muted dash. */
function OddsPair({ prices, pickOver }: { prices: Prices; pickOver: boolean }) {
  const side = (price: number | null, picked: boolean) => (
    <span className={picked ? (price === null ? "on none" : "on") : undefined}>
      {formatOdds(price)}
    </span>
  );
  return (
    <>
      {side(prices.over, pickOver)}
      <span className="sep">/</span>
      {side(prices.under, !pickOver)}
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

const GAME_STATES: { value: GameState; label: string }[] = [
  { value: "all", label: "All" },
  { value: "pre", label: "Pre-game" },
  { value: "live", label: "Live" },
];

/** The zero-result row's list of what is narrowing the board: "DAL (NBA), +EV only and “kyr”". */
function activeSummary(options: Record<FacetKey, MenuOption[]>, filters: Filters): string {
  const parts = activePicks(options, filters).map((chip) => chip.label);
  if (filters.plusEvOnly) parts.push("+EV only");
  if (filters.gameState !== "all") {
    parts.push(filters.gameState === "live" ? "Live" : "Pre-game");
  }
  if (filters.text.trim()) parts.push(`“${filters.text.trim()}”`);
  return parts.length > 1 ? `${parts.slice(0, -1).join(", ")} and ${parts.at(-1)}` : parts[0];
}

function FilterBar({
  options,
  counts,
  filters,
  onChange,
  searchRef,
  filtersButtonRef,
  count,
  shown,
}: {
  options: Record<FacetKey, MenuOption[]>;
  /** Each category's "All …" count. */
  counts: Record<FacetKey, number>;
  filters: Filters;
  onChange: (change: Partial<Filters>) => void;
  searchRef: RefObject<HTMLInputElement | null>;
  filtersButtonRef: RefObject<HTMLButtonElement | null>;
  count: string;
  shown: number;
}) {
  return (
    <>
      <div className="filters" role="group" aria-label="Filters">
        <button
          type="button"
          className="evt"
          aria-pressed={filters.plusEvOnly}
          onClick={() => onChange({ plusEvOnly: !filters.plusEvOnly })}
        >
          +EV only
        </button>
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
        <FiltersPopup
          options={options}
          filters={filters}
          onChange={onChange}
          counts={counts}
          shown={shown}
          triggerRef={filtersButtonRef}
        />
        <SearchBox text={filters.text} onText={(text) => onChange({ text })} inputRef={searchRef} />
        <span className="count" aria-live="polite">
          {count}
        </span>
      </div>
      <ChipRow
        options={options}
        filters={filters}
        onChange={onChange}
        filtersButtonRef={filtersButtonRef}
      />
    </>
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

export function BoardTable({ rows, teamNames }: { rows: BoardRow[]; teamNames: TeamNames }) {
  const [open, setOpen] = useState<number | null>(null);
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [sort, setSort] = useState<Sort>(DEFAULT_SORT);
  const [shownCount, setShownCount] = useState(PAGE_SIZE);
  /** Position of the first row a "Show more" added, to bring into view once it renders. */
  const [revealFrom, setRevealFrom] = useState<number | null>(null);
  const gridRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const filtersButtonRef = useRef<HTMLButtonElement>(null);

  const columns = useMemo(() => columnsFor(rows), [rows]);
  const props = useMemo(
    () => rows.map((row, id): Prop => ({ id, row, search: searchEntry(row, teamNames) })),
    [rows, teamNames],
  );
  // `?search=classic` brings back the old search for side-by-side testing; this branch only.
  const [classic, setClassic] = useState(false);
  useEffect(() => {
    setClassic(new URLSearchParams(window.location.search).get("search") === "classic");
  }, []);
  const query = useMemo(() => parseQuery(filters.text), [filters.text]);
  const matching = useMemo(
    () =>
      sorted(
        props.filter(({ row, search }) =>
          classic
            ? matches(row, filters, teamNames)
            : passesFilters(row, filters) && matchesQuery(search, query),
        ),
        sort,
      ),
    [props, filters, sort, teamNames, classic, query],
  );
  const { options, all } = useMemo(
    () => filterMenus(rows, filters, teamNames),
    [rows, filters, teamNames],
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
  // The zero-result row's buttons vanish with it, so focus goes to what each one cleared.
  const clearPicks = () => {
    changeFilters(NO_PICKS);
    filtersButtonRef.current?.focus();
  };
  const clearSearch = () => {
    changeFilters({ text: "" });
    searchRef.current?.focus();
  };
  const picked = pickCount(filters) > 0;
  const typed = filters.text.trim() !== "";
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
        options={options}
        counts={all}
        filters={filters}
        onChange={changeFilters}
        searchRef={searchRef}
        filtersButtonRef={filtersButtonRef}
        count={breakdown(matching)}
        shown={matching.length}
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
                  No props match {activeSummary(options, filters)}.{" "}
                  {picked && (
                    <button type="button" className="link" onClick={clearPicks}>
                      Clear filters
                    </button>
                  )}
                  {picked && typed && " · "}
                  {typed && (
                    <button type="button" className="link" onClick={clearSearch}>
                      Clear search
                    </button>
                  )}
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
    </>
  );
}
