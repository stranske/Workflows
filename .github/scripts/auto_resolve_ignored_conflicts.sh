#!/usr/bin/env bash
# Auto-resolve conflicts in files that should use "ours" merge strategy
# These files are PR-specific and should keep the PR branch version when conflicts occur
#
# Usage: ./auto_resolve_ignored_conflicts.sh <base_branch>
#
# This script:
# 1. Fetches the latest base branch
# 2. Attempts to merge base into the current branch
# 3. For known PR-specific files, auto-resolves using --ours
# 4. Commits the resolution if successful

set -e

BASE_BRANCH="${1:-main}"

# Files that should always keep the PR branch version (configured in .gitattributes with merge=ours)
# but need manual resolution since the git driver isn't configured
IGNORED_CONFLICT_FILES=(
  "pr_body.md"
  "ci/autofix/history.json"
  "keepalive-metrics.ndjson"
  "coverage-trend-history.ndjson"
  "metrics-history.ndjson"
  "residual-trend-history.ndjson"
)

echo "=== Auto-Resolve Ignored Conflict Files ==="
echo "Base branch: $BASE_BRANCH"

# Fetch latest base
echo "Fetching origin/$BASE_BRANCH..."
git fetch origin "$BASE_BRANCH" --quiet

# Check if we're already up to date
if git merge-base --is-ancestor "origin/$BASE_BRANCH" HEAD 2>/dev/null; then
  echo "✓ Branch is already up to date with $BASE_BRANCH"
  exit 0
fi

# Try to merge - this may create conflicts
echo "Attempting merge from origin/$BASE_BRANCH..."
if git merge "origin/$BASE_BRANCH" --no-edit 2>/dev/null; then
  echo "✓ Merge completed without conflicts"
  exit 0
fi

# Merge failed - check for conflicts in ignored files
echo "Merge has conflicts. Checking for auto-resolvable files..."

RESOLVED_COUNT=0
REMAINING_CONFLICTS=()

# Get list of unmerged files
while IFS= read -r conflict_file; do
  [ -z "$conflict_file" ] && continue

  SHOULD_AUTO_RESOLVE=false
  for ignored in "${IGNORED_CONFLICT_FILES[@]}"; do
    if [[ "$conflict_file" == "$ignored" || "$conflict_file" == *"/$ignored" ]]; then
      SHOULD_AUTO_RESOLVE=true
      break
    fi
  done

  if $SHOULD_AUTO_RESOLVE; then
    echo "  → Auto-resolving: $conflict_file (keeping ours)"
    git checkout --ours "$conflict_file" 2>/dev/null || true
    git add "$conflict_file" 2>/dev/null || true
    ((RESOLVED_COUNT++))
  else
    REMAINING_CONFLICTS+=("$conflict_file")
  fi
done < <(git diff --name-only --diff-filter=U 2>/dev/null)

if [ "$RESOLVED_COUNT" -gt 0 ]; then
  echo "✓ Auto-resolved $RESOLVED_COUNT file(s)"
fi

if [ ${#REMAINING_CONFLICTS[@]} -eq 0 ]; then
  # All conflicts resolved - commit
  echo "All conflicts resolved. Committing..."
  git commit -m "fix: auto-resolve PR-specific file conflicts with $BASE_BRANCH

Files resolved using --ours strategy:
$(for f in "${IGNORED_CONFLICT_FILES[@]}"; do echo "- $f"; done)

These files are PR-specific and should not inherit content from the base branch."
  echo "✓ Merge conflict resolution committed"
  exit 0
else
  echo ""
  echo "⚠ Remaining conflicts require manual resolution:"
  for f in "${REMAINING_CONFLICTS[@]}"; do
    echo "  - $f"
  done
  echo ""
  echo "Run 'git status' to see conflict details."
  exit 1
fi
