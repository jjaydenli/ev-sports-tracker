import { BoardTable } from "@/components/BoardTable";
import { StatusPill } from "@/components/StatusPill";
import { TipLayer } from "@/components/Tip";
import { SITE_NAME, SOURCE_URL, fetchBoard } from "@/lib/board";

// ISR: visitors get the cached page; only the background revalidation waits on the API.
// Next reads this segment config statically, so it cannot import REVALIDATE_SECONDS
// (lib/board.ts, the fetch cache window). Keep the two equal.
export const revalidate = 300;

export default async function Page() {
  const { board, latest_run: latestRun, team_names: teamNames = {} } = await fetchBoard();

  return (
    <main>
      <header>
        <div className="topbar">
          <h1 className="brand">
            <img src="/icon.svg" alt="" width={32} height={32} />
            {SITE_NAME}
          </h1>
          <a className="source-link" href={SOURCE_URL} aria-label="Source on GitHub">
            <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
              <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
            </svg>
            GitHub
          </a>
        </div>
        <p className="lede">
          Each Betr pick&apos;em prop&apos;s fair hit chance from sportsbook no-vig odds, against
          Betr&apos;s breakeven. Select a row for the breakdown.
        </p>
        <StatusPill run={latestRun} board={board} />
      </header>
      {board ? (
        <BoardTable rows={board.props} teamNames={teamNames} />
      ) : (
        <p className="empty">No board has been published yet.</p>
      )}
      {/* Page level, not inside the table: the status pill's tip needs it with no board too. */}
      <TipLayer />
    </main>
  );
}
