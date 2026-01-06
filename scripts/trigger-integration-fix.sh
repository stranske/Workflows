#!/usr/bin/env bash
# Script to trigger the integration tests formatting fix workflow
# Usage: ./scripts/trigger-integration-fix.sh [commit_message]

set -euo pipefail

COMMIT_MESSAGE="${1:-fix: Auto-format files to meet lint standards}"

echo "🚀 Triggering integration tests formatting fix..."
echo "Commit message: $COMMIT_MESSAGE"

# Check if gh CLI is available
if ! command -v gh &> /dev/null; then
    echo "❌ Error: gh CLI is not installed"
    echo "Install it from: https://cli.github.com/"
    exit 1
fi

# Trigger the workflow
gh workflow run maint-70-fix-integration-formatting.yml \
  --repo stranske/Workflows \
  -f commit_message="$COMMIT_MESSAGE"

echo "✅ Workflow triggered successfully!"
echo ""
echo "View progress at:"
echo "https://github.com/stranske/Workflows/actions/workflows/maint-70-fix-integration-formatting.yml"
echo ""
echo "After the workflow completes, verify integration tests pass at:"
echo "https://github.com/stranske/Workflows-Integration-Tests/actions"
