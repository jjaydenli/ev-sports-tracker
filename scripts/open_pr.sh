#!/usr/bin/env bash
# Push branch, run pre-PR gates, open prefilled create-PR page (default) or gh pr create.
set -euo pipefail

if git rev-parse --show-toplevel >/dev/null 2>&1; then
  REPO_ROOT="$(git rev-parse --show-toplevel)"
else
  REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
fi
cd "$REPO_ROOT"

BASE_BRANCH="main"
MODE="auto"
DO_PUSH=0
SKIP_ARCH_CHECK=0

usage() {
  cat <<'EOF'
Usage: ./scripts/open_pr.sh [options] [base-branch]

  Default: push + open GitHub compare page (title + body prefilled).

Options:
  --create           gh pr create (or title-only edit if the PR exists), then open PR page
  --manual           Print title, body, and compare URL (no push/browser)
  --push             Push branch (with --manual, skip opening PR)
  --skip-arch-check  Skip architecture-sync guard
  -h, --help         Show help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --create) MODE="create"; shift ;;
    --manual) MODE="manual"; shift ;;
    --push) DO_PUSH=1; shift ;;
    --skip-arch-check) SKIP_ARCH_CHECK=1; shift ;;
    -h | --help) usage; exit 0 ;;
    -*)
      echo "error: unknown option $1" >&2
      usage >&2
      exit 1
      ;;
    *) BASE_BRANCH="$1"; shift ;;
  esac
done

CURRENT="$(git branch --show-current)"
if [[ "$CURRENT" == "main" || "$CURRENT" == "master" ]]; then
  echo "error: create a topic branch before preparing a PR (on: $CURRENT)" >&2
  exit 1
fi

if ! git rev-parse --verify "$BASE_BRANCH" >/dev/null 2>&1; then
  echo "error: base branch '$BASE_BRANCH' not found locally" >&2
  exit 1
fi

LOG_BASE="$BASE_BRANCH"
if [[ "$BASE_BRANCH" == "main" || "$BASE_BRANCH" == "master" ]] \
  && git rev-parse --verify "origin/${BASE_BRANCH}" >/dev/null 2>&1; then
  local_sha="$(git rev-parse "$BASE_BRANCH")"
  remote_sha="$(git rev-parse "origin/${BASE_BRANCH}")"
  if [[ "$local_sha" != "$remote_sha" ]] \
    && git merge-base --is-ancestor "$local_sha" "$remote_sha"; then
    echo "note: local $BASE_BRANCH is behind origin/$BASE_BRANCH; using origin for PR range" >&2
    LOG_BASE="origin/${BASE_BRANCH}"
  fi
fi

if [[ -z "$(git rev-list "${LOG_BASE}..HEAD" 2>/dev/null || true)" ]]; then
  echo "error: no commits on $CURRENT since $LOG_BASE" >&2
  exit 1
fi

build_pr_body() {
  PR_BASE="$LOG_BASE" python3 <<'PY'
import os, subprocess
base = os.environ["PR_BASE"]
subjects = [
    line for line in subprocess.run(
        ["git", "log", f"{base}..HEAD", "--reverse", "--format=%s"],
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    if line.strip()
]
bullets = "\n".join(f"- {s}" for s in subjects)
print(
    f"## Summary\n\n{bullets}\n\n"
    f"## Test plan\n\n- [x] `cd backend && pytest -q`\n\n"
    f"## Commits\n\n{bullets}"
)
PY
}

url_encode() {
  python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$1"
}

github_repo_slug() {
  local remote url
  remote="$(git remote get-url origin 2>/dev/null || true)"
  case "$remote" in
    git@github.com:*) url="${remote#git@github.com:}" ;;
    https://github.com/*) url="${remote#https://github.com/}" ;;
    *)
      echo "error: cannot parse GitHub owner/repo from origin: $remote" >&2
      exit 1
      ;;
  esac
  printf '%s' "${url%.git}"
}

build_compare_url() {
  printf 'https://github.com/%s/compare/%s...%s?quick_pull=1&title=%s&body=%s' \
    "$(github_repo_slug)" "$BASE_BRANCH" "$CURRENT" \
    "$(url_encode "$TITLE")" "$(url_encode "$BODY")"
}

copy_body() {
  command -v pbcopy >/dev/null 2>&1 || return 0
  printf '%s\n' "$BODY" | pbcopy
  echo "description copied to clipboard"
}

require_gh() {
  if ! command -v gh >/dev/null 2>&1; then
    echo "error: gh CLI not found (brew install gh && gh auth login)" >&2
    exit 1
  fi
  if ! gh auth status >/dev/null 2>&1; then
    echo "error: gh not authenticated (gh auth login)" >&2
    exit 1
  fi
}

TITLE="$(git log "${LOG_BASE}..HEAD" --reverse --format=%s | head -1)"
BODY="$(build_pr_body)"

if [[ "$SKIP_ARCH_CHECK" == 0 ]]; then
  ./scripts/check_arch_sync.sh "$LOG_BASE"
fi

if [[ "$MODE" == "auto" ]]; then
  if command -v open >/dev/null 2>&1 || command -v xdg-open >/dev/null 2>&1; then
    MODE="browser"
  else
    MODE="manual"
  fi
fi

if [[ "$MODE" == "create" || "$MODE" == "browser" || "$DO_PUSH" == 1 ]]; then
  echo "pushing $CURRENT to origin..."
  git push -u origin HEAD
fi

if [[ "$MODE" == "create" ]]; then
  require_gh
  if gh pr view --json number >/dev/null 2>&1; then
    # Never overwrite a PR's body here: it may have been hand-written since creation, and
    # this script's generated body (a bare commit-subject list) is strictly weaker. Update
    # the title only; use `gh pr edit --body-file <file>` directly to change the body.
    echo "PR exists; updating title only (body left as-is)..."
    gh pr edit --title "$TITLE"
  else
    body_file="$(mktemp)"
    trap 'rm -f "$body_file"' EXIT
    printf '%s\n' "$BODY" >"$body_file"
    echo "creating PR: $TITLE"
    gh pr create --base "$BASE_BRANCH" --title "$TITLE" --body-file "$body_file"
  fi
  gh pr view --web 2>/dev/null || gh pr view
  exit 0
fi

if [[ "$MODE" == "browser" ]]; then
  if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1 \
    && gh pr view --json number >/dev/null 2>&1; then
    echo "PR already exists; opening..."
    gh pr view --web 2>/dev/null || gh pr view
    exit 0
  fi
  copy_body
  compare_url="$(build_compare_url)"
  echo "opening create-PR page..."
  if command -v open >/dev/null 2>&1; then
    open "$compare_url"
  else
    xdg-open "$compare_url"
  fi
  echo "$compare_url"
  exit 0
fi

# --manual
echo "Title: $TITLE"
echo ""
echo "$BODY"
echo ""
copy_body || true
echo "Compare URL:"
echo "  $(build_compare_url)"
if [[ "$DO_PUSH" == 0 ]]; then
  echo ""
  echo "Push: git push -u origin HEAD"
fi
