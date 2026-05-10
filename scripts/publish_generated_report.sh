#!/usr/bin/env bash

set -euo pipefail

if [ "$#" -lt 2 ]; then
  echo "Usage: $0 <commit-message> <path> [<path> ...]" >&2
  exit 2
fi

commit_message="$1"
shift

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

git add -- "$@"

if git diff --cached --quiet; then
  echo "No report changes to commit."
  exit 0
fi

git commit -m "$commit_message"

for attempt in 1 2 3; do
  if git push origin HEAD:main; then
    echo "Push succeeded on attempt $attempt."
    exit 0
  fi

  if [ "$attempt" -eq 3 ]; then
    echo "Push failed after $attempt attempts." >&2
    exit 1
  fi

  echo "Push failed on attempt $attempt, fetching and rebasing onto origin/main." >&2
  git fetch origin main
  git rebase origin/main
done
