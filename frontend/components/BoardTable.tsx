"use client";

import { Fragment, type ReactNode, useEffect, useMemo, useRef, useState } from "react";

import { TipLayer } from "@/components/Tip";

import {
  BETR,
  type Book,
  type BoardRow,
  DASH,
  F,
  PRICED_BOOKS,
  americanToPct,
  bool,
  bookPrices,
  edgePts,
  edgeStep,
  formatOdds,
  formatPct,
  formatSignedPct,
  hasPrices,
  holdPct,
  lineSourceWords,
  marketWords,
  matchup,
  num,
  oneSidedCaveat,
  pctToAmerican,
  pickLine,
  str,
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
  cell: (row: BoardRow) => ReactNode;
};

type GameState = "all" | "pre" | "live";

type Filters = {
  plusEvOnly: boolean;
  league: string;
  gameState: GameState;
  market: string;
  game: string;
  player: string;
};

const NO_FILTERS: Filters = {
  plusEvOnly: false,
  league: "",
  gameState: "all",
  market: "",
  game: "",
  player: "",
};

const DEFAULT_SORT: Sort = { key: "hit", dir: -1 };

/**
 * Rows shown at first, and added by each "Show more". Growing one list instead of numbered
 * pages keeps every earlier match on screen; filters and sort still cover the whole board.
 */
const PAGE_SIZE = 50;

function matches(row: BoardRow, f: Filters): boolean {
  const query = f.player.trim().toLowerCase();
  return (
    (!f.plusEvOnly || bool(row, F.plusEv)) &&
    (!f.league || str(row, F.league) === f.league) &&
    (f.gameState === "all" || (f.gameState === "live") === bool(row, F.isLive)) &&
    (!f.market || str(row, F.market) === f.market) &&
    (!f.game || str(row, F.game) === f.game) &&
    (!query || (str(row, F.player) ?? "").toLowerCase().includes(query))
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

/** The distinct values of one key on the board, sorted, for a filter's options. */
function distinct(rows: BoardRow[], key: string): string[] {
  const values = new Set<string>();
  for (const row of rows) {
    const value = str(row, key);
    if (value !== null) values.add(value);
  }
  return [...values].sort();
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
  const step = edgeStep(edgePts(row));
  const tip =
    hit === null
      ? undefined
      : `Hit ${formatPct(hit, 2)} · breakeven ${formatPct(breakeven, 2)} · fair ${formatOdds(pctToAmerican(hit))}`;
  return (
    <span className="mstack" data-tip={tip}>
      <span className={step ? `hit e${step}` : "hit"}>{formatPct(hit)}</span>
      <span className="evline">{formatSignedPct(num(row, F.evPct))} EV</span>
    </span>
  );
}

function BookCell({ row, book }: { row: BoardRow; book: Book }) {
  const prices = bookPrices(row, book);
  if (!hasPrices(prices)) return <span className="none">{DASH}</span>;
  const pickOver = str(row, F.side) === "over";
  const hold = holdPct(prices.over, prices.under);
  const tip =
    `${book.name}: over ${formatOdds(prices.over)}, under ${formatOdds(prices.under)}` +
    (hold === null ? "" : ` · hold ${hold.toFixed(1)}%`);
  return (
    <span className="slash" data-tip={tip}>
      <span className={pickOver ? "on" : undefined}>{formatOdds(prices.over)}</span>
      <span className="sep">/</span>
      <span className={pickOver ? undefined : "on"}>{formatOdds(prices.under)}</span>
    </span>
  );
}

function Detail({ row }: { row: BoardRow }) {
  const why = whySentence(row);
  const caveat = oneSidedCaveat(row);
  const books = PRICED_BOOKS.filter((book) => hasPrices(bookPrices(row, book)));
  return (
    <div className="detail-inner">
      <p className="why">
        {why.verdict && <strong>{why.verdict}</strong>} {why.reason}
      </p>
      <dl className="facts">
        <div>
          <dt>Fair hit chance (no vig)</dt>
          <dd>{formatPct(num(row, F.hitPct), 2)}</dd>
        </div>
        <div>
          <dt>Betr breakeven</dt>
          <dd>{formatPct(num(row, F.betrBreakevenPct), 2)}</dd>
        </div>
        <div>
          <dt>EV</dt>
          <dd>{formatSignedPct(num(row, F.evPct))}</dd>
        </div>
        <div>
          <dt>Price source</dt>
          <dd className="plain">{lineSourceWords(row)}</dd>
        </div>
      </dl>
      {books.length > 0 && (
        <table className="books">
          <thead>
            <tr>
              <th scope="col">Book</th>
              <th scope="col" className="num">Line</th>
              <th scope="col" className="num">Over</th>
              <th scope="col" className="num">Under</th>
              <th scope="col" className="num">Implied o / u (with vig)</th>
              <th scope="col" className="num">Hold</th>
            </tr>
          </thead>
          <tbody>
            {books.map((book) => {
              const { over, under } = bookPrices(row, book);
              return (
                <tr key={book.key}>
                  <td>
                    <span className="bookname">
                      <Logo book={book} />
                      {book.name}
                    </span>
                  </td>
                  <td className="num">{num(row, F.line) ?? DASH}</td>
                  <td className="num">{formatOdds(over)}</td>
                  <td className="num">{formatOdds(under)}</td>
                  <td className="num">
                    {formatPct(americanToPct(over))} / {formatPct(americanToPct(under))}
                  </td>
                  <td className="num">{formatPct(holdPct(over, under))}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
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
      className: "num metric",
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

function SelectFilter({
  label,
  value,
  options,
  words = (option) => option,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  words?: (option: string) => string;
  onChange: (value: string) => void;
}) {
  return (
    <label className={value ? "field set" : "field"}>
      {label}
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">All</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {words(option)}
          </option>
        ))}
      </select>
    </label>
  );
}

const GAME_STATES: { value: GameState; label: string }[] = [
  { value: "all", label: "All" },
  { value: "pre", label: "Pre-game" },
  { value: "live", label: "Live" },
];

function isFiltered(filters: Filters): boolean {
  return (Object.keys(NO_FILTERS) as (keyof Filters)[]).some(
    (key) => filters[key] !== NO_FILTERS[key],
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
  return (
    <div className="filters" role="group" aria-label="Filters">
      <label className={filters.plusEvOnly ? "toggle on" : "toggle"}>
        <input
          type="checkbox"
          checked={filters.plusEvOnly}
          onChange={(event) => onChange({ plusEvOnly: event.target.checked })}
        />
        +EV only
      </label>
      <SelectFilter
        label="League"
        value={filters.league}
        options={distinct(rows, F.league)}
        onChange={(league) => onChange({ league })}
      />
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
      <SelectFilter
        label="Market"
        value={filters.market}
        options={distinct(rows, F.market)}
        words={marketWords}
        onChange={(market) => onChange({ market })}
      />
      <SelectFilter
        label="Game"
        value={filters.game}
        options={distinct(rows, F.game)}
        onChange={(game) => onChange({ game })}
      />
      <input
        type="search"
        className={filters.player ? "set" : undefined}
        placeholder="Player"
        aria-label="Search player"
        value={filters.player}
        onChange={(event) => onChange({ player: event.target.value })}
      />
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
                    className="prop"
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
                      <td key={col.id} className={col.className}>
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
