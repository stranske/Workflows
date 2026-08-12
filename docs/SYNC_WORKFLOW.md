# Workflow Sync Process

## Purpose
Prevent propagating bugs to consumer repos by validating changes in the source (Workflows) repo before syncing.

## Before Any Sync

### 0. Verify Template Sync (CRITICAL)

**If you modified `.github/scripts/` or another manifest-declared exact template-sync file, ensure templates are synced:**

```bash
# Check for out-of-sync templates
python scripts/validate_template_sync.py

# If validation fails:
./scripts/sync_templates.sh

# Verify fixed:
python scripts/validate_template_sync.py

# Commit template changes:
git add templates/consumer-repo/<changed-path>
git commit -m "sync: update templates with latest script changes"
```

**Why?** Consumer repos sync from `templates/consumer-repo/`. If exact-sync source files are changed but templates aren't updated, no sync PRs will be created with those changes.

The CI workflow `health-72-template-sync.yml` enforces this, but check manually before triggering sync.

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

## Stable Delivery PRs

Maint 68 coalesces canary updates into `sync/workflows-candidate` and promoted
updates into `sync/workflows-delivery`. It updates the same PR in place. Before
an actual push it disables auto-merge, converts the PR to draft, and adds
`sync:delivery-staging`; if the computed base/tree is unchanged it preserves
the existing review lifecycle.

Maint 71 is the sole merge/close authority. It marks staging PRs ready for
bounded review, requires one available reviewer response after seven minutes
(or degrades after an all-capacity signal / fifteen-minute no-response
timeout), and never waives active review threads. It seals the exact head,
triggers a fresh Gate, and merges only after that Gate succeeds. The staging
label blocks shared merge lanes until Maint 71 completes the merge.

### Reconcile the stable lanes
```bash
gh workflow run maint-71-merge-sync-prs.yml \
  --repo stranske/Workflows \
  -f active_sync_hash=candidate
```

```bash
gh workflow run maint-71-merge-sync-prs.yml \
  --repo stranske/Workflows \
  -f active_sync_hash=delivery
```

Do not use direct `gh pr merge`, admin merge, or auto-merge on these stable
branches. Re-run Maint 71 after the recorded quiet-period/check timestamp.

## Summary Checklist

- [ ] Run ruff/mypy/tests in Workflows repo
- [ ] Fix any issues found
- [ ] Check for open sync PRs across all consumer repos
- [ ] Refresh each stable candidate or delivery PR in place through Maint 68
- [ ] Keep refreshed PRs draft and labeled `sync:delivery-staging`
- [ ] Use Maint 71 to start the review window, settle available reviewer evidence, and seal the exact head
- [ ] Verify zero active non-outdated review threads and passing required checks on the sealed head
- [ ] Let Maint 71 merge only the sealed stable delivery; use its reconciliation output for stale attempts
- [ ] If issues found, fix in Workflows and re-sync (do NOT fix in consumers)
