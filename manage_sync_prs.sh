#!/bin/bash
set -euo pipefail

# Manage sync PRs in consumer repos using CODESPACES secret
# This script:
# 1. Closes stale sync PRs (keeps only the latest)
# 2. Checks status of remaining PRs
# 3. Reports which PRs are ready to merge

if [ -z "${CODESPACES:-}" ]; then
  echo "Error: CODESPACES secret not found" >&2
  exit 1
fi

# Use CODESPACES token for gh CLI (overrides GITHUB_TOKEN)
export GH_TOKEN="$CODESPACES"

REPOS=(
  "Travel-Plan-Permission"
  "Template"
  "trip-planner"
  "Manager-Database"
  "Portable-Alpha-Extension-Model"
  "Trend_Model_Project"
  "Collab-Admin"
)

echo "=== Managing Sync PRs in Consumer Repos ==="
echo ""

# Step 1: Close stale PRs
echo "Step 1: Closing stale sync PRs..."
echo ""

for repo in "${REPOS[@]}"; do
  echo "Checking stranske/$repo..."

  # Get all open sync PRs sorted by creation date (oldest first)
  prs=$(gh pr list --repo "stranske/$repo" --state open \
    --search "head:sync/workflows" \
    --json number,createdAt,headRefName \
    --jq 'sort_by(.createdAt) | .[] | "\(.number):\(.headRefName)"' || echo "")

  if [ -z "$prs" ]; then
    echo "  → No sync PRs found"
    continue
  fi

  # Count PRs
  pr_count=$(echo "$prs" | wc -l | tr -d ' ')

  if [ "$pr_count" -eq 1 ]; then
    pr_num=$(echo "$prs" | cut -d: -f1)
    echo "  → 1 sync PR: #$pr_num (keeping)"
    continue
  fi

  echo "  → Found $pr_count sync PRs, closing $((pr_count - 1)) stale..."

  # Process all except the last one
  stale_prs=$(echo "$prs" | head -n -1)
  latest_pr=$(echo "$prs" | tail -n 1 | cut -d: -f1)

  while IFS=: read -r pr_num branch_name; do
    echo "    Closing #$pr_num..."
    if gh pr close "$pr_num" --repo "stranske/$repo" \
      --comment "Superseded by newer sync PR #$latest_pr" \
      --delete-branch 2>&1 | grep -q "^$"; then
      echo "      ✓ Closed and deleted branch"
    else
      echo "      ✓ Closed"
    fi
  done <<< "$stale_prs"

  echo "    Keeping #$latest_pr"
done

echo ""
echo "Step 2: Checking status of remaining PRs..."
echo ""

# Step 2: Check status of remaining PRs
READY_TO_MERGE=()
HAS_FAILURES=()
CHECKS_PENDING=()

for repo in "${REPOS[@]}"; do
  # Get the open sync PR (should be only one now)
  pr_num=$(gh pr list --repo "stranske/$repo" --state open \
    --search "head:sync/workflows" \
    --json number --jq '.[0].number' 2>/dev/null || echo "")

  if [ -z "$pr_num" ] || [ "$pr_num" = "null" ]; then
    continue
  fi

  echo "Checking stranske/$repo #$pr_num..."

  # Get PR status
  pr_data=$(gh pr view "$pr_num" --repo "stranske/$repo" \
    --json state,mergeable,statusCheckRollup 2>/dev/null || echo "{}")

  if [ "$pr_data" = "{}" ]; then
    echo "  ⚠ Could not fetch PR data"
    continue
  fi

  mergeable=$(echo "$pr_data" | jq -r '.mergeable')

  # Count check statuses
  success=$(echo "$pr_data" | jq '[.statusCheckRollup[] | select(.conclusion == "SUCCESS")] | length')
  failure=$(echo "$pr_data" | jq '[.statusCheckRollup[] | select(.conclusion == "FAILURE")] | length')
  pending=$(echo "$pr_data" | jq '[.statusCheckRollup[] | select(.conclusion == null or .conclusion == "")] | length')

  echo "  Mergeable: $mergeable | ✓ $success | ✗ $failure | ⏳ $pending"

  if [ "$mergeable" = "MERGEABLE" ] && [ "$failure" = "0" ] && [ "$pending" = "0" ]; then
    echo "  ✅ READY TO MERGE"
    READY_TO_MERGE+=("$repo:$pr_num")
  elif [ "$failure" -gt 0 ]; then
    echo "  ❌ HAS FAILURES"
    HAS_FAILURES+=("$repo:$pr_num")
  elif [ "$pending" -gt 0 ]; then
    echo "  ⏳ CHECKS PENDING"
    CHECKS_PENDING+=("$repo:$pr_num")
  fi
done

echo ""
echo "=== Summary ==="
echo ""
echo "✅ Ready to merge: ${#READY_TO_MERGE[@]}"
for item in "${READY_TO_MERGE[@]}"; do
  echo "   - stranske/${item%%:*} #${item##*:}"
done
echo ""
echo "❌ Has failures: ${#HAS_FAILURES[@]}"
for item in "${HAS_FAILURES[@]}"; do
  echo "   - stranske/${item%%:*} #${item##*:}"
done
echo ""
echo "⏳ Checks pending: ${#CHECKS_PENDING[@]}"
for item in "${CHECKS_PENDING[@]}"; do
  echo "   - stranske/${item%%:*} #${item##*:}"
done
echo ""

if [ ${#HAS_FAILURES[@]} -gt 0 ]; then
  echo "❌ Some PRs have failing checks - investigation needed"
  exit 1
fi

if [ ${#READY_TO_MERGE[@]} -gt 0 ]; then
  echo "✅ ${#READY_TO_MERGE[@]} PR(s) ready to merge"
  echo ""
  echo "To merge all ready PRs, run:"
  for item in "${READY_TO_MERGE[@]}"; do
    repo="${item%%:*}"
    pr_num="${item##*:}"
    echo "  gh pr merge $pr_num --repo stranske/$repo --merge --delete-branch"
  done
fi

echo ""
echo "Done!"
