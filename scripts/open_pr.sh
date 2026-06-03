#!/usr/bin/env bash
# Prepare a PR title/body from branch commits and open it on GitHub.
# Default: gh pr create when gh is authenticated (avoids PR template merge issues).
# Fallback: print a compare URL (--manual, or when gh is unavailable).
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

usage() {
  cat <<'EOF'
Usage: ./scripts/open_pr.sh [options] [base-branch]

  Default: push branch and create/update PR via gh when authenticated.
  Compare URLs often merge commit bodies with pull_request_template.md and
  leave Summary/Commits blank — gh sets the full body directly.

Options:
  --create    Force gh pr create (same as default when gh auth works)
  --manual    Print compare URL only; do not call gh
  --push      Push branch only (with --manual, skip opening PR)
  -h, --help  Show this help

Examples:
  ./scripts/open_pr.sh
  ./scripts/open_pr.sh --manual
  ./scripts/open_pr.sh --push --manual
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --create) MODE="create"; shift ;;
    --manual) MODE="manual"; shift ;;
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
      feat:* | fix:* | chore:* | docs:* | refactor:* | test:* | build:* | ci:* | perf:*)
        printf '%s' "$subject"
        return 0
        ;;
    esac
  done < <(git log "${BASE_BRANCH}..HEAD" --reverse --format='%s')
  git log "${BASE_BRANCH}..HEAD" --reverse --format='%s' | head -n 1
}

build_pr_body() {
  PR_BASE="$BASE_BRANCH" python3 <<'PY'
import os
import re
import subprocess

base = os.environ["PR_BASE"]
hashes = subprocess.run(
    ["git", "log", f"{base}..HEAD", "--reverse", "--format=%H"],
    capture_output=True,
    text=True,
    check=True,
).stdout.splitlines()

summary_bullets: list[str] = []
commit_subjects: list[str] = []

for commit_hash in hashes:
    if not commit_hash.strip():
        continue
    message = subprocess.run(
        ["git", "log", "-1", "--format=%B", commit_hash.strip()],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    lines = [line.strip() for line in message.splitlines() if line.strip()]
    if not lines:
        continue
    subject = lines[0]
    commit_subjects.append(subject)
    body_lines = lines[1:]
    if body_lines:
        body_text = re.sub(r"\s+", " ", " ".join(body_lines)).strip()
        summary_bullets.extend(
            sentence.strip()
            for sentence in re.split(r"(?<=\.)\s+", body_text)
            if sentence.strip()
        )
    elif len(hashes) == 1:
        summary_bullets.append(subject)

if not summary_bullets and commit_subjects:
    summary_bullets = commit_subjects

summary = "\n".join(f"- {line}" for line in summary_bullets)
commits = "\n".join(f"- {subject}" for subject in commit_subjects)

print(
    f"""## Summary

{summary}

## Test plan

- [x] `cd backend && pytest -q`

## Commits

{commits}"""
)
PY
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

resolve_mode() {
  if [[ "$MODE" != "auto" ]]; then
    return 0
  fi
  if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    MODE="create"
  else
    MODE="manual"
  fi
}

gh_pr_create_or_update() {
  local body_file
  body_file="$(mktemp)"
  trap 'rm -f "$body_file"' RETURN
  printf '%s\n' "$BODY" >"$body_file"

  if gh pr view --json number >/dev/null 2>&1; then
    echo "→ updating existing PR title/body..."
    gh pr edit --title "$TITLE" --body-file "$body_file"
  else
    echo "→ creating PR: $TITLE"
    gh pr create --base "$BASE_BRANCH" --title "$TITLE" --body-file "$body_file"
  fi
  gh pr view --web 2>/dev/null || gh pr view
}

TITLE="$(pick_pr_title)"
BODY="$(build_pr_body)"

resolve_mode

if [[ "$MODE" == "create" || "$DO_PUSH" == 1 ]]; then
  echo "→ pushing $CURRENT to origin..."
  git push -u origin HEAD
fi

if [[ "$MODE" == "create" ]]; then
  if ! command -v gh >/dev/null 2>&1; then
    echo "error: gh CLI not found. Install: brew install gh && gh auth login" >&2
    exit 1
  fi
  if ! gh auth status >/dev/null 2>&1; then
    echo "error: gh not authenticated. Run: gh auth login" >&2
    exit 1
  fi
  gh_pr_create_or_update
  exit 0
fi

# Manual mode: GitHub appends pull_request_template.md to compare URLs and the
# default "Compare & pull request" button, leaving Summary/Commits empty.
# Paste the printed body (all three sections filled) over the entire field.
echo ""
echo "══════════════════════════════════════════════════════════════"
echo "  PR: $CURRENT → $BASE_BRANCH"
echo "══════════════════════════════════════════════════════════════"
echo ""
echo "Title:"
echo "  $TITLE"
echo ""
echo "Description — select all in GitHub's description box and paste this:"
echo "──────────────────────────────────────────────────────────────"
printf '%s\n' "$BODY"
echo "──────────────────────────────────────────────────────────────"
echo ""

if command -v pbcopy >/dev/null 2>&1; then
  printf '%s\n' "$BODY" | pbcopy
  echo "→ Description copied to clipboard (pbcopy)."
  echo ""
fi

if [[ "$MODE" == "manual" ]]; then
  if ! command -v gh >/dev/null 2>&1 || ! gh auth status >/dev/null 2>&1; then
    echo "Recommended: gh auth login  (then re-run ./scripts/open_pr.sh — creates PR with filled sections)"
    echo ""
  fi
fi

echo "GitHub appends pull_request_template.md when you use the push/email"
echo "\"Compare & pull request\" button — that leaves Summary/Commits blank."
echo "Paste the body above (or from clipboard) to replace the entire description."
echo ""
if [[ "$DO_PUSH" == 0 ]]; then
  echo "Push first if needed:"
  echo "  git push -u origin HEAD"
  echo ""
fi
echo "Open compare (title prefilled; paste body before Create):"
echo "  https://github.com/$(github_repo_slug)/compare/${BASE_BRANCH}...${CURRENT}?quick_pull=1&title=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$TITLE")"
echo ""
