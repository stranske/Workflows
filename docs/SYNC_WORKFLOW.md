# Workflow Sync Process

## Purpose
Prevent propagating bugs to consumer repos by validating changes in the source (Workflows) repo before syncing.

## Before Any Sync

### 1. Validate in Workflows Repo
```bash
# In /workspaces/Workflows
cd /workspaces/Workflows

# Run all validation checks
python -m ruff check .
python -m mypy tools/ scripts/ .github/scripts/
python -m pytest tests/ -x

# If any fail, fix them BEFORE syncing
```

### 2. Check for Existing Sync Issues
```bash
# Check open sync PRs across all consumer repos
for repo in "consumer-repo-1" "consumer-repo-2" "consumer-repo-3"; do
    echo "=== $repo ==="
    gh pr list --repo "stranske/$repo" --search "sync" --state open \
        --json number,title,createdAt | jq -c '.[] | {num: .number, created: .createdAt}'
done
```

### 3. Review Bot Comments on Latest Sync PRs
```bash
# For each repo with open sync PRs, check bot comments on the LATEST one
for repo in "consumer-repo-1" "consumer-repo-2" "consumer-repo-3"; do
    latest=$(gh pr list --repo "stranske/$repo" --search "sync" --state open \
        --json number --jq '.[0].number')
    if [ -n "$latest" ]; then
        echo "=== $repo PR #$latest ==="
        gh api "repos/stranske/$repo/pulls/$latest/comments" \
            --jq '.[] | select(.user.login | contains("bot")) |
                  {path, line, body: .body[0:200]}'
    fi
done
```

## Fixing Issues Found

### If Validation Fails in Workflows
1. Fix the issue in Workflows repo
2. Create PR for the fix
3. Get it merged to main
4. THEN trigger sync
5. Do NOT manually fix in consumer repos - let sync propagate the fix

### If Bot Comments Found
1. Address in Workflows source if it's a template issue
2. Document if it's expected (like models:read permission)
3. Do NOT merge sync PRs until issues are resolved or documented

## Handling Multiple Sync PRs

### Close Duplicates (Keep Latest)
```bash
# For repos with multiple sync PRs, close all but the newest
for repo in "consumer-repo-1" "consumer-repo-2" "consumer-repo-3"; do
    prs=$(gh pr list --repo "stranske/$repo" --search "sync" --state open \
        --json number --jq '.[].number' | sort -n)
    count=$(echo "$prs" | wc -l)
    if [ "$count" -gt 1 ]; then
        to_close=$(echo "$prs" | head -n $((count-1)))
        for pr in $to_close; do
            echo "Closing $repo #$pr (duplicate)"
            gh pr close "$pr" --repo "stranske/$repo"
        done
    fi
done
```

## Merging Clean Sync PRs

### Check Status Before Merge
```bash
repo="Manager-Database"
pr="163"

# Verify: 1) No failing checks, 2) No unresolved bot comments, 3) Mergeable
gh pr view "$pr" --repo "stranske/$repo" --json mergeable,statusCheckRollup \
    | jq '{mergeable, failing: [.statusCheckRollup[] |
           select(.conclusion == "FAILURE") | .name]}'
```

### Batch Merge
```bash
# Only merge PRs that pass all checks and have no bot issues
for repo in "consumer-repo-1" "consumer-repo-2" "consumer-repo-3"; do
    latest=$(gh pr list --repo "stranske/$repo" --search "sync" --state open \
        --json number --jq '.[0].number')
    if [ -n "$latest" ]; then
        # Check if it's clean
        failing=$(gh pr view "$latest" --repo "stranske/$repo" --json statusCheckRollup \
            --jq '[.statusCheckRollup[] | select(.conclusion == "FAILURE")] | length')
        if [ "$failing" = "0" ]; then
            echo "Merging $repo #$latest"
            gh pr merge "$latest" --repo "stranske/$repo" --squash --admin
        else
            echo "SKIP $repo #$latest - has failing checks"
        fi
    fi
done
```

## Summary Checklist

- [ ] Run ruff/mypy/tests in Workflows repo
- [ ] Fix any issues found
- [ ] Check for open sync PRs across all consumer repos
- [ ] Review bot comments on latest sync PRs
- [ ] Address or document any bot concerns
- [ ] Close duplicate sync PRs (keep only latest)
- [ ] Verify latest PRs have no failing checks
- [ ] Merge clean PRs
- [ ] If issues found, fix in Workflows and re-sync (do NOT fix in consumers)
