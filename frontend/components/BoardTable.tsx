"use client";

import { Fragment, type ReactNode, useState } from "react";

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

type Column = {
  id: string;
  header: ReactNode;
  className?: string;
  cell: (row: BoardRow) => ReactNode;
};

function Logo({ book }: { book: Book }) {
  return (
    <span className="logo" tabIndex={0} title={book.name}>
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
        <span className="be" title={`Betr breakeven ${formatPct(breakeven, 2)}`}>
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
    <span className="mstack" title={tip}>
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
    <span className="slash" title={tip}>
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
      className: "sticky-col",
      cell: (row) => <PlayerCell row={row} />,
    },
    {
      id: "hit",
      header: "Hit %",
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

export function BoardTable({ rows }: { rows: BoardRow[] }) {
  const [open, setOpen] = useState<number | null>(null);

  if (!rows.length) {
    return <p className="empty">No props on the board.</p>;
  }

  const columns = columnsFor(rows);
  const props: Prop[] = rows.map((row, id) => ({ id, row }));

  return (
    <div className="grid">
      <table className="board">
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col.id} scope="col" className={col.className}>
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {props.map(({ id, row }) => {
            const isOpen = open === id;
            const toggle = () => setOpen(isOpen ? null : id);
            return (
              <Fragment key={id}>
                <tr
                  className="prop"
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
        </tbody>
      </table>
    </div>
  );
}
