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
        <h1>Betr +EV Prop Optimizer</h1>
        <p className="lede">
          Each Betr pick&apos;em prop&apos;s fair hit chance from sportsbook no-vig odds, against
          Betr&apos;s breakeven. Select a row for the breakdown.
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
