"use client";

import { Fragment, useState } from "react";

import {
  type BoardRow,
  DASH,
  F,
  bool,
  formatOdds,
  formatPct,
  num,
  str,
} from "@/lib/board";

const PAGE_SIZE = 25;
const COLUMN_COUNT = 11;

function rowKey(row: BoardRow, index: number): string {
  return [str(row, F.player), str(row, F.market), num(row, F.line), str(row, F.side), index].join(
    "|",
  );
}

function teamGame(row: BoardRow): string {
  const parts = [str(row, F.team), str(row, F.game)].filter(Boolean);
  if (parts.length) return parts.join(" · ");
  return str(row, F.league) ?? DASH;
}

function oddsPair(row: BoardRow, overKey: string, underKey: string): string {
  const over = num(row, overKey);
  const under = num(row, underKey);
  if (over === null && under === null) return DASH;
  return `${formatOdds(over)} / ${formatOdds(under)}`;
}

function source(row: BoardRow): string {
  const lineSource = str(row, F.lineSource) ?? DASH;
  return bool(row, F.corroborated) ? `${lineSource} ✓` : lineSource;
}

function sharpByBook(row: BoardRow): [string, string][] {
  const value = row[F.sharpByBook];
  if (!value || typeof value !== "object") return [];
  return Object.entries(value as Record<string, unknown>).map(([book, how]) => [
    book,
    typeof how === "string" ? how : DASH,
  ]);
}

function Breakdown({ row }: { row: BoardRow }) {
  const books = sharpByBook(row);
  const favored = str(row, F.noVigFavoredSide);
  return (
    <dl className="breakdown">
      <div>
        <dt>No-vig fair probability{favored ? ` (${favored})` : ""}</dt>
        <dd>{formatPct(num(row, F.noVigImpliedPct), 2)}</dd>
      </div>
      <div>
        <dt>Hit probability, this side</dt>
        <dd>{formatPct(num(row, F.hitPct), 2)}</dd>
      </div>
      <div>
        <dt>Betr breakeven</dt>
        <dd>{formatPct(num(row, F.betrBreakevenPct), 2)}</dd>
      </div>
      <div>
        <dt>Sharp books used</dt>
        <dd>
          {books.length
            ? books.map(([book, how]) => `${book} (${how})`).join(", ")
            : DASH}
        </dd>
      </div>
    </dl>
  );
}

export function BoardTable({ rows }: { rows: BoardRow[] }) {
  const [page, setPage] = useState(0);
  const [open, setOpen] = useState<string | null>(null);

  const pageCount = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const current = Math.min(page, pageCount - 1);
  const start = current * PAGE_SIZE;
  const visible = rows.slice(start, start + PAGE_SIZE);

  if (!rows.length) {
    return <p className="empty">No props on the board.</p>;
  }

  return (
    <>
      <div className="table-scroll">
        <table className="board">
          <thead>
            <tr>
              <th scope="col">Player</th>
              <th scope="col">Team / Game</th>
              <th scope="col">Market</th>
              <th scope="col" className="num">Line</th>
              <th scope="col">Side</th>
              <th scope="col" className="num">EV%</th>
              <th scope="col" className="num">Hit%</th>
              <th scope="col" className="num">Betr breakeven</th>
              <th scope="col" className="num">DK O/U</th>
              <th scope="col" className="num">FD O/U</th>
              <th scope="col">Src</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((row, offset) => {
              const key = rowKey(row, start + offset);
              const isOpen = open === key;
              return (
                <Fragment key={key}>
                  <tr className={bool(row, F.plusEv) ? "plus-ev" : undefined}>
                    <td>
                      <button
                        type="button"
                        className="expand"
                        aria-expanded={isOpen}
                        onClick={() => setOpen(isOpen ? null : key)}
                      >
                        <span aria-hidden="true">{isOpen ? "▾" : "▸"}</span>{" "}
                        {str(row, F.player) ?? DASH}
                      </button>
                    </td>
                    <td>{teamGame(row)}</td>
                    <td>{str(row, F.market) ?? DASH}</td>
                    <td className="num">{num(row, F.line) ?? DASH}</td>
                    <td>{str(row, F.side) ?? DASH}</td>
                    <td className="num ev">{formatPct(num(row, F.evPct), 2)}</td>
                    <td className="num">{formatPct(num(row, F.hitPct))}</td>
                    <td className="num">{formatPct(num(row, F.betrBreakevenPct))}</td>
                    <td className="num">{oddsPair(row, F.dkOver, F.dkUnder)}</td>
                    <td className="num">{oddsPair(row, F.fdOver, F.fdUnder)}</td>
                    <td>{source(row)}</td>
                  </tr>
                  {isOpen && (
                    <tr className="breakdown-row">
                      <td colSpan={COLUMN_COUNT}>
                        <Breakdown row={row} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      <nav className="pager" aria-label="Board pages">
        <button type="button" onClick={() => setPage(current - 1)} disabled={current === 0}>
          Previous
        </button>
        <span>
          Rows {start + 1}–{start + visible.length} of {rows.length}
        </span>
        <button
          type="button"
          onClick={() => setPage(current + 1)}
          disabled={current >= pageCount - 1}
        >
          Next
        </button>
      </nav>
    </>
  );
}
