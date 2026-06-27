#!/usr/bin/env bash
# Pre-flight arch-sync check — called by open_pr.sh before pushing.
# Exits 1 with actionable messages if backend changes on this branch
# lack corresponding architecture doc updates.
set -euo pipefail

if git rev-parse --show-toplevel >/dev/null 2>&1; then
  REPO_ROOT="$(git rev-parse --show-toplevel)"
else
  REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
fi
cd "$REPO_ROOT"

BASE_REF="${1:-origin/main}"
if ! git rev-parse --verify "$BASE_REF" >/dev/null 2>&1; then
  BASE_REF="main"
fi

[[ ! -f project_context.md ]] && exit 0

mapfile -t changed < <(git diff --name-only "${BASE_REF}...HEAD" 2>/dev/null | sort -u)
[[ ${#changed[@]} -eq 0 ]] && exit 0

arch=0 book=0 runner=0 ctx=0 readme=0 debug=0 skills=0
for p in "${changed[@]}"; do
  case "$p" in
    project_context.md) ctx=1 ;;
    README.md) readme=1 ;;
  esac
  [[ "$p" =~ ^backend/(scrapers|parsers|core|config|archive)/ \
     || "$p" =~ ^docs/betting_odds/ \
  [[ "$p" == "backend/config/pipeline_sources.py" \
     || "$p" =~ ^backend/scrapers/sportsbooks/.*_engine\.py$ ]] && book=1 && arch=1
  [[ "$p" == "backend/core/pipeline_runner.py" ]] && runner=1 && arch=1
done
((arch == 0)) && exit 0

msgs=()
((ctx == 0)) && msgs+=("  - project_context.md §3/§5/§6 not updated")
((book && !readme)) && msgs+=("  - README.md sharp-book list may need updating")
((runner && !debug)) && msgs+=("  - debug-pipeline.md may have stale CLI flags")
[[ ${#msgs[@]} -eq 0 ]] && exit 0

echo "error: arch docs out of sync with backend changes on this branch:" >&2
for m in "${msgs[@]}"; do echo "$m" >&2; done
echo "" >&2
echo "Update and commit the above before opening the PR." >&2
echo "Use --skip-plan-check to bypass if this is a docs-only PR." >&2
exit 1
