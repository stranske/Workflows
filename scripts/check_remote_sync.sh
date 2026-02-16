#!/bin/bash
# Pre-push hook: Ensure local branch is not behind its remote AND includes the latest main.
#
# Why both checks?
# - Staying synced with remote/$branch prevents push rejections.
# - Including remote/main prevents pushing commits that will immediately conflict in the PR.

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

# Also require that this branch includes the latest remote main.
# This prevents pushing commits that will create merge conflicts against main.
echo "Checking if branch includes latest $remote/main..."
if git fetch "$remote" main --quiet 2>/dev/null; then
    if ! git merge-base --is-ancestor "$remote/main" HEAD; then
        echo ""
        echo "❌ ERROR: Your branch does not include the latest $remote/main"
        echo ""
        echo "   Before pushing, run ONE of:"
        echo "     git fetch $remote main"
        echo "     git rebase $remote/main   # preferred"
        echo "     # or"
        echo "     git merge $remote/main"
        echo ""
        echo "   To see what's different:"
        echo "     git log $remote/main..HEAD --oneline"
        echo ""
        exit 1
    fi
else
    echo "⚠️  Warning: could not fetch $remote/main; skipping main-sync check"
fi

echo "✓ Branch includes latest $remote/main"
exit 0
