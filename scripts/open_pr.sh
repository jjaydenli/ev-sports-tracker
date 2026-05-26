#!/usr/bin/env bash
# Prepare a PR title/body from branch commits. Default: print autofill link (you open the PR).
# Optional: --create pushes and runs gh pr create (requires gh auth).
set -euo pipefail

if git rev-parse --show-toplevel >/dev/null 2>&1; then
  REPO_ROOT="$(git rev-parse --show-toplevel)"
else
  REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
fi
cd "$REPO_ROOT"

BASE_BRANCH="main"
MODE="manual"
DO_PUSH=0

usage() {
  cat <<'EOF'
Usage: ./scripts/open_pr.sh [options] [base-branch]

  Default (manual): print PR title, description, and a GitHub compare URL with
  title/body prefilled. You open the link and click "Create pull request".

Options:
  --create    Push branch and create/update PR via gh (requires gh auth login)
  --push      Push branch before printing manual link
  -h, --help  Show this help

Examples:
  ./scripts/open_pr.sh
  ./scripts/open_pr.sh --push
  ./scripts/open_pr.sh --create
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --create) MODE="create"; shift ;;
    --push) DO_PUSH=1; shift ;;
    -h | --help)
      usage
      exit 0
      ;;
    main | master | develop)
      BASE_BRANCH="$1"
      shift
      ;;
    -*)
      echo "error: unknown option $1" >&2
      usage >&2
      exit 1
      ;;
    *)
      BASE_BRANCH="$1"
      shift
      ;;
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

if [[ -z "$(git rev-list "${BASE_BRANCH}..HEAD" 2>/dev/null || true)" ]]; then
  echo "error: no commits on $CURRENT since $BASE_BRANCH" >&2
  exit 1
fi

pick_pr_title() {
  local subject
  while IFS= read -r subject; do
    case "$subject" in
      feat:* | fix:*)
        printf '%s' "$subject"
        return 0
        ;;
    esac
  done < <(git log "${BASE_BRANCH}..HEAD" --reverse --format='%s')
  git log "${BASE_BRANCH}..HEAD" --reverse --format='%s' | head -n 1
}

build_pr_body() {
  local title="$1"
  local commits
  commits="$(git log "${BASE_BRANCH}..HEAD" --reverse --format='- %s')"
  cat <<EOF
## Summary

${title}

## Test plan

- [x] \`cd backend && pytest -q\`

## Commits

${commits}
EOF
}

github_repo_slug() {
  local remote url
  remote="$(git remote get-url origin 2>/dev/null || true)"
  case "$remote" in
    git@github.com:*)
      url="${remote#git@github.com:}"
      url="${url%.git}"
      ;;
    https://github.com/*)
      url="${remote#https://github.com/}"
      url="${url%.git}"
      ;;
    *)
      echo "error: cannot parse GitHub owner/repo from origin: $remote" >&2
      exit 1
      ;;
  esac
  printf '%s' "$url"
}

build_compare_url() {
  local slug="$1"
  local title="$2"
  local body="$3"
  PR_TITLE="$title" PR_BODY="$body" PR_BASE="$BASE_BRANCH" PR_HEAD="$CURRENT" PR_SLUG="$slug" \
    python3 <<'PY'
import os
import urllib.parse

slug = os.environ["PR_SLUG"]
base = os.environ["PR_BASE"]
head = os.environ["PR_HEAD"]
title = os.environ["PR_TITLE"]
body = os.environ["PR_BODY"]

query = urllib.parse.urlencode(
    {"quick_pull": "1", "title": title, "body": body},
    quote_via=urllib.parse.quote,
)
print(f"https://github.com/{slug}/compare/{base}...{head}?{query}")
PY
}

TITLE="$(pick_pr_title)"
BODY="$(build_pr_body "$TITLE")"
SLUG="$(github_repo_slug)"
COMPARE_URL="$(build_compare_url "$SLUG" "$TITLE" "$BODY")"

if [[ "$MODE" == "create" || "$DO_PUSH" == 1 ]]; then
  echo "→ pushing $CURRENT to origin..."
  git push -u origin HEAD
fi

if [[ "$MODE" == "create" ]]; then
  if ! command -v gh >/dev/null 2>&1; then
    echo "error: gh CLI not found. Install: brew install gh && gh auth login" >&2
    exit 1
  fi
  if gh pr view --json number >/dev/null 2>&1; then
    echo "→ updating existing PR title/body..."
    gh pr edit --title "$TITLE" --body "$BODY"
    gh pr view --web 2>/dev/null || gh pr view
  else
    echo "→ creating PR: $TITLE"
    gh pr create --base "$BASE_BRANCH" --title "$TITLE" --body "$BODY"
    gh pr view --web 2>/dev/null || gh pr view
  fi
  exit 0
fi

# Manual mode: user opens the compare URL themselves.
echo ""
echo "══════════════════════════════════════════════════════════════"
echo "  PR: $CURRENT → $BASE_BRANCH"
echo "══════════════════════════════════════════════════════════════"
echo ""
echo "Title (also prefilled in link):"
echo "  $TITLE"
echo ""
echo "Description (copy if needed; also prefilled in link):"
echo "──────────────────────────────────────────────────────────────"
printf '%s\n' "$BODY"
echo "──────────────────────────────────────────────────────────────"
echo ""
if [[ "$DO_PUSH" == 0 ]]; then
  echo "Before opening, push your branch:"
  echo "  git push -u origin HEAD"
  echo ""
fi
echo "Open this URL to create the PR (title + body autofill):"
echo "  $COMPARE_URL"
echo ""
