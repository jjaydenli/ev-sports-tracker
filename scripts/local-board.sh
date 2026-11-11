#!/usr/bin/env bash
# The local board: the board page over this checkout's ./ev runs.
# Run as `npm run dev` from the repo root. API on 127.0.0.1:8000 (backend
# web/local_board.py), page on http://localhost:3000; Ctrl-C stops both. A run started
# from the page is detached and keeps going; its output is in
# backend/data/processed/local_run.log.
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

# Stop every process in this group (uvicorn, next dev) on Ctrl-C or any exit.
trap 'trap - INT TERM EXIT; kill 0' INT TERM EXIT

echo "Local board. Terminal runs: ./ev --top-n all"

(
  cd "$ROOT/backend"
  exec .venv/bin/uvicorn web.local_board:app --host 127.0.0.1 --port "$API_PORT"
) &

(
  cd "$ROOT/frontend"
  export BOARD_API_URL="http://127.0.0.1:$API_PORT"
  export BOARD_LOCAL=1
  exec node_modules/.bin/next dev --port "$PAGE_PORT"
) &

wait
