#!/bin/bash
# Pre-push hook: Ensure local branch is not behind its remote AND includes the latest main.
#
# Why both checks?
# - Staying synced with remote/$branch prevents push rejections.
# - Including remote/main prevents pushing commits that will immediately conflict in the PR.

set -euo pipefail

# Get the remote being pushed to (passed by git)
remote="${1:-origin}"

# Detached pushes do not identify a current branch for this check.
branch=$(git rev-parse --abbrev-ref HEAD)
if [[ "$branch" == HEAD ]]; then
    echo "Detached HEAD, skipping branch sync check"
    exit 0
fi

# Determine the remote default branch (usually origin/main).
# Using refs/remotes/<remote>/HEAD makes this resilient if default changes.
default_ref=$(git symbolic-ref -q --short "refs/remotes/${remote}/HEAD" || true)
if [[ -z "$default_ref" ]]; then
    default_ref="${remote}/main"
fi
default_branch="${default_ref#"$remote"/}"
default_remote_branch="${remote}/${default_branch}"

# Git returns 2 for no matching ref. A transport error proves no such absence.
if git ls-remote --exit-code --heads "$remote" "refs/heads/$branch" >/dev/null; then
    :
else
    status=$?
    if [[ "$status" -eq 2 ]]; then
        echo "✓ New branch, no remote to sync with"
        exit 0
    fi
    echo "❌ ERROR: Could not inspect $remote/$branch (Git exit $status)" >&2
    exit "$status"
fi

fetch_tip() {
    local name="$1" status
    git fetch --quiet "$remote" "refs/heads/$name" || {
        status=$?
        echo "❌ ERROR: Could not fetch $remote/$name (Git exit $status)" >&2
        return "$status"
    }
    # Use the fetched commit even when the remote's refspec omits this branch.
    git rev-parse --verify 'FETCH_HEAD^{commit}'
}

remote_branch_ref="$remote/$branch"
echo "Checking if branch is synced with $remote_branch_ref..."
remote_tip=$(fetch_tip "$branch")

# Always require that this branch includes the latest remote default branch.
echo "Checking if branch includes latest $default_remote_branch..."
default_tip=$(fetch_tip "$default_branch")
if git merge-base --is-ancestor "$default_tip" HEAD; then
    echo "✓ Branch includes latest $default_remote_branch"
else
    status=$?
    if [[ "$status" -ne 1 ]]; then
        echo "❌ ERROR: Could not compare HEAD with $default_remote_branch (Git exit $status)" >&2
        exit "$status"
    fi
    echo ""
    echo "❌ ERROR: Your branch does not include the latest $default_remote_branch"
    echo ""
    echo "   Before pushing, run ONE of:"
    echo "     git fetch $remote $default_branch"
    echo "     git rebase $default_remote_branch   # preferred"
    echo "   # or"
    echo "     git merge $default_remote_branch"
    echo ""
    echo "   To see what's different:"
    echo "     git log $default_remote_branch..HEAD --oneline"
    echo ""
    exit 1
fi

# Remote-sync check (non-blocking for rebases):
#
# If the remote branch has commits that aren't in our local HEAD, that usually means we're behind.
# But after a rebase, the remote will appear "ahead" by old commit SHAs even if the content is
# already in the default branch. In that case, blocking pushes is counterproductive.
#
# We only fail if the remote has commits NOT in HEAD AND NOT already in the default branch.
behind=$(git rev-list --count "HEAD..$remote_tip")
if [ "$behind" -gt 0 ]; then
    # Count commits that exist on the remote branch but are neither in HEAD nor in default branch.
    remote_unique_not_in_default=$(git rev-list --count "HEAD..$remote_tip" --not "$default_tip")

    if [ "$remote_unique_not_in_default" -gt 0 ]; then
        # This usually means one of:
        # - You are genuinely behind and need to pull/rebase.
        # - You rebased locally (rewrote history) and intend to force-push.
        #
        # We can't reliably detect `git push --force-with-lease` from here, so require an explicit
        # opt-in env var for the rebase/force-push workflow.
        if [[ "${ALLOW_NON_FAST_FORWARD_PUSH:-}" == "1" ]]; then
            echo "⚠️  Override enabled (ALLOW_NON_FAST_FORWARD_PUSH=1): allowing non-fast-forward update of $remote_branch_ref"
        else
            echo ""
            echo "❌ ERROR: Your branch is missing $remote_unique_not_in_default commit(s) from $remote_branch_ref"
            echo ""
            echo "   If you are behind, run:"
            echo "     git pull --rebase"
            echo ""
            echo "   If you rebased and intend to force-push safely, run:"
            echo "     ALLOW_NON_FAST_FORWARD_PUSH=1 git push --force-with-lease"
            echo ""
            echo "   Or to see what's different:"
            echo "     git log HEAD..$remote_branch_ref --oneline"
            echo ""
            exit 1
        fi
    fi

    echo "⚠️  Note: $remote_branch_ref has commits not in HEAD, but they are already in $default_remote_branch."
    echo "   This is typical after rebasing; you may need: git push --force-with-lease"
else
    echo "✓ Branch is in sync with remote"
fi
exit 0
