#!/usr/bin/env bash
# The local board: the board page over this checkout's ./ev runs.
# Run as `npm run dev` from the repo root. API on 127.0.0.1:8000 (backend
# web/local_board.py), page on http://localhost:3000. Ctrl-C, the page's Shut down, or
# either server exiting stops both, and ends any run the page started. Page-run output
# is in backend/data/processed/local_run.log.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_PORT=8000
PAGE_PORT=3000

if [[ ! -x "$ROOT/backend/.venv/bin/uvicorn" ]]; then
  echo "local-board: backend/.venv is missing uvicorn; see Setup in README.md" >&2
  exit 1
fi
if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
  echo "local-board: run 'npm --prefix frontend ci' first" >&2
  exit 1
fi

# Stop every process in this group (uvicorn, next dev) on Ctrl-C or any exit. uvicorn's
# shutdown ends a page-started run, which lives in its own process group.
trap 'trap - INT TERM EXIT; kill 0' INT TERM EXIT

echo "Local board. Terminal runs: ./ev --top-n all"

(
  cd "$ROOT/backend"
  exec .venv/bin/uvicorn web.local_board:app --host 127.0.0.1 --port "$API_PORT"
) &
API_PID=$!

(
  cd "$ROOT/frontend"
  export BOARD_API_URL="http://127.0.0.1:$API_PORT"
  export BOARD_LOCAL=1
  exec node_modules/.bin/next dev --port "$PAGE_PORT"
) &
PAGE_PID=$!

# One server down means both down. /bin/bash 3.2 has no `wait -n`, so poll both PIDs.
while kill -0 "$API_PID" 2>/dev/null && kill -0 "$PAGE_PID" 2>/dev/null; do
  sleep 1
done
echo "local-board: a server exited; stopping the other" >&2
