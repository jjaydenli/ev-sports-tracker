import { BoardTable } from "@/components/BoardTable";
import { StatusPill } from "@/components/StatusPill";
import { fetchBoard } from "@/lib/board";

// ISR: visitors get the cached page; only the background revalidation waits on the API.
// Next reads this segment config statically, so it cannot import REVALIDATE_SECONDS
// (lib/board.ts, the fetch cache window). Keep the two equal.
export const revalidate = 300;

export default async function Page() {
  const { board, latest_run: latestRun } = await fetchBoard();

  return (
    <main>
      <header>
        <h1>EV board</h1>
        <p className="lede">
          Betr pick&apos;em props priced against DraftKings and FanDuel. EV% compares each
          side&apos;s no-vig hit probability with Betr&apos;s breakeven; +EV rows are
          highlighted. Select a player for the breakdown.
        </p>
        <StatusPill run={latestRun} board={board} />
      </header>
      {board ? (
        <BoardTable rows={board.props} />
      ) : (
        <p className="empty">No board has been published yet.</p>
      )}
    </main>
  );
}
