#!/bin/bash
# Script to manually trigger the integration repo sync workflow
# This is useful when you need to push template changes immediately
# without waiting for a commit to main branch

set -euo pipefail

REPO="stranske/Workflows"
WORKFLOW="maint-69-sync-integration-repo.yml"

echo "🚀 Triggering Integration Repo Sync workflow..."
echo "Repository: $REPO"
echo "Workflow: $WORKFLOW"
echo ""

# Check if GH_TOKEN is set
if [ -z "${GH_TOKEN:-}" ]; then
    echo "⚠️  GH_TOKEN not set. The gh CLI will use your default authentication."
fi

# Trigger the workflow
if gh workflow run "$WORKFLOW" --repo "$REPO" --ref main; then
    echo "✅ Workflow triggered successfully!"
    echo ""
    echo "Monitor progress at:"
    echo "https://github.com/$REPO/actions/workflows/$WORKFLOW"
    echo ""
    echo "To view recent runs:"
    echo "  gh run list --repo $REPO --workflow=\"$WORKFLOW\" --limit 5"
else
    echo "❌ Failed to trigger workflow"
    exit 1
fi
