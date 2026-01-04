#!/bin/bash
# Script to close PRs created by the faulty sync on 2026-01-03 at 17:41
# These PRs contain DOWNGRADED package versions and should NOT be merged

set -e

CLOSE_MESSAGE="🚨 **WARNING: Contains downgraded versions - DO NOT MERGE**

This PR contains DOWNGRADED package versions due to a bug in the Workflows repo template files:
- PyYAML: 6.0.3 → 6.0.2 ❌
- Pydantic: 2.12.5 → 2.10.3 ❌
- Pydantic-core: 2.41.5 → 2.27.1 ❌
- Hypothesis: 6.148.9 → 6.115.1 ❌
- jsonschema: 4.25.1 → 4.22.0 ❌

**Root cause:** Template files in Workflows repo had stale versions that weren't updated when runtime deps were removed.

**Action:** Closing this PR. A corrected sync will be triggered after stranske/Workflows#488 is merged.

See: stranske/Workflows#488"

echo "Closing faulty sync PRs from 2026-01-03..."
echo ""

# Array of repo:pr_number pairs
declare -a PRS=(
  "stranske/Trend_Model_Project:4149"
  "stranske/Portable-Alpha-Extension-Model:967"
  "stranske/Travel-Plan-Permission:194"
  "stranske/Template:61"
  "stranske/trip-planner:57"
  "stranske/Manager-Database:141"
)

for pr_info in "${PRS[@]}"; do
  repo="${pr_info%:*}"
  pr_num="${pr_info#*:}"

  echo "Processing $repo #$pr_num..."

  # Add comment
  if gh pr comment "$pr_num" --repo "$repo" --body "$CLOSE_MESSAGE" 2>/dev/null; then
    echo "  ✓ Added warning comment"
  else
    echo "  ⚠ Could not add comment (may need auth)"
  fi

  # Close PR
  if gh pr close "$pr_num" --repo "$repo" 2>/dev/null; then
    echo "  ✓ Closed PR"
  else
    echo "  ⚠ Could not close PR (may need manual action)"
  fi

  echo ""
done

echo "Done! Please verify all PRs are closed:"
echo ""
for pr_info in "${PRS[@]}"; do
  repo="${pr_info%:*}"
  pr_num="${pr_info#*:}"
  echo "  https://github.com/$repo/pull/$pr_num"
done
