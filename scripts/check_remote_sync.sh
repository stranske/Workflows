#!/bin/bash
# Pre-push hook: Ensure local branch is not behind remote
# Prevents the frustrating "push rejected, please pull" cycle

set -euo pipefail

# Get the remote being pushed to (passed by git)
remote="${1:-origin}"

# Get current branch
branch=$(git rev-parse --abbrev-ref HEAD)

# Skip for new branches that don't exist on remote yet
if ! git ls-remote --exit-code --heads "$remote" "$branch" &>/dev/null; then
    echo "✓ New branch, no remote to sync with"
    exit 0
fi

# Fetch latest (quietly)
echo "Checking if branch is synced with $remote/$branch..."
git fetch "$remote" "$branch" --quiet 2>/dev/null || true

# Count commits we're behind
behind=$(git rev-list --count HEAD.."$remote/$branch" 2>/dev/null || echo "0")

if [ "$behind" -gt 0 ]; then
    echo ""
    echo "❌ ERROR: Your branch is $behind commit(s) behind $remote/$branch"
    echo ""
    echo "   Before pushing, run:"
    echo "     git pull --rebase"
    echo ""
    echo "   Or to see what's different:"
    echo "     git log HEAD..$remote/$branch --oneline"
    echo ""
    exit 1
fi

echo "✓ Branch is in sync with remote"
exit 0
