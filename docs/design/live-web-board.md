# Live board

## Context

The board existed only as a terminal table on one machine. The goal is one public URL showing the
latest real board and its scrape time, refreshed on a schedule, needing nothing from the visitor.

## Decisions

- **GitHub Actions scrapes, FastAPI on Render stores, Postgres on Neon holds, Next.js on Vercel
  shows.** The scrape cannot run on Render or Vercel, so the job pushes its result and the web side
  never holds Betr credentials. Neon because Render's free Postgres is deleted after 30 days and
  Supabase's free tier pauses after a week idle. FastAPI sits in front of the database to validate
  what the job posts and keep database credentials off the frontend.
- **ISR hides the sleeping API.** Render's free tier sleeps after 15 minutes and takes about a
  minute to wake. The page revalidates every 300 s, so visitors get the cached page. A failed fetch
  throws instead of rendering an error, which keeps the last good page cached.
- **Only a clean, same-run board replaces the published one.** A run attaches its board when `./ev`
  exited 0, the board's `run_id` matches the coverage, and it has rows. Every other run posts
  health only, so the page can say a scrape failed while still showing the last good board.
- **One `board_runs` table with rows stored as opaque JSON.** The API validates the envelope, not
  the row schema, which the engine owns. A repeat POST of a `run_id` upserts, so retries are safe.
- **Public workflow logs carry warnings and one coverage line, never props.** `./ev`'s full output
  goes to a runner temp file that is never uploaded.
- **Whole board, capped at 2000 rows in the publisher.** Capping in the API would mean rejecting
  the POST, which would also drop that run's health record.

## Rejected

- **Committing board JSON to the repo and serving a static page.** No servers, but git history is
  public and permanent, so the prices could never be put behind a passcode later.
- **A refresh button.** It would have to dispatch a workflow (minutes, not seconds), put a GitHub
  token on the server, and need a cooldown on an open site. The status pill shows the board's age
  instead.
