# Skill: Consumer Repo Sync Process

**Location**: Workflows repo only (not synced to consumers)

**Trigger**: When syncing workflow updates to consumer repos, or when consumer repo CI fails after sync

## The Problem

Syncing workflow template changes to consumer repos often causes CI failures because:
1. Consumer repos have different configurations
2. Workflow changes may have untested interactions
3. Multiple repos failing means repetitive debugging

## The Process

### Phase 1: Pre-Sync Validation (on Workflows)

Before triggering sync to consumers:

1. **Run local tests**: `pytest tests/ -v`
2. **Validate sync manifest**: Check `.github/sync-manifest.yml` is complete
3. **Check template syntax**: Validate YAML in `templates/consumer-repo/.github/workflows/*.yml`
4. **Review changes**: What files changed since last sync?

```bash
# Check what will be synced
git diff origin/main~1..origin/main -- templates/consumer-repo/
```

### Phase 2: Controlled Sync (One Repo First)

**Never sync to all repos at once.** Start with one test repo:

1. **Pick test repo**: Use Template or a low-risk consumer
2. **Run manual sync**:
   ```bash
   gh workflow run maint-68-sync-consumer-repos.yml \
     --repo stranske/Workflows \
     -f repos="stranske/Template" \
     -f dry_run=false
   ```
3. **Wait for PR creation**: Watch for the sync PR
4. **Monitor CI**: Wait for ALL checks to complete

### Phase 3: Verify CI Success

After sync PR is created:

1. **Check Gate workflow**: Must pass completely
2. **Check CI workflow**: All jobs must succeed
3. **Review file changes**: Ensure only expected files changed

```bash
gh pr checks <PR_NUMBER> --repo stranske/Template
```

### Phase 4: Handle Failures

If CI fails on the test repo:

1. **DO NOT sync to other repos yet**
2. **Analyze failure**:
   ```bash
   gh run view <RUN_ID> --repo stranske/Template --log-failed
   ```
3. **Determine fix location**:
   - If fix needed in Workflows → Fix in Workflows, re-sync
   - If fix needed in consumer → Consumer-specific issue
4. **Close/abandon the failing sync PR**
5. **Fix the root cause in Workflows repo**
6. **Re-run from Phase 2**

### Phase 5: Rollout to All Repos

Only after test repo passes:

1. **Trigger full sync**:
   ```bash
   gh workflow run maint-68-sync-consumer-repos.yml \
     --repo stranske/Workflows \
     -f repos="" \
     -f dry_run=false
   ```
2. **Monitor all PRs**: Check each consumer repo's PR
3. **Batch handle failures**: If multiple fail with same error, fix once in Workflows

### Phase 6: Rollback (if needed)

If sync causes widespread failures:

1. **Identify the breaking commit** in Workflows
2. **Revert in Workflows**:
   ```bash
   git revert <BREAKING_COMMIT>
   ```
3. **Close all failing sync PRs** without merging
4. **Re-sync with reverted changes**

## Quick Reference Commands

```bash
# List recent sync workflow runs
gh run list --repo stranske/Workflows --workflow maint-68-sync-consumer-repos.yml --limit 5

# Check sync PR status across consumers
for repo in Template Travel-Plan-Permission Manager-Database; do
  echo "=== $repo ===" 
  gh pr list --repo stranske/$repo --search "sync:" --limit 1
done

# Dry run sync to preview changes
gh workflow run maint-68-sync-consumer-repos.yml \
  --repo stranske/Workflows \
  -f dry_run=true
```

## Common Sync Failure Patterns

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Workflow syntax error | Invalid YAML in template | Fix in `templates/consumer-repo/` |
| Missing dependency | Workflow uses action not in consumer | Add to workflow or manifest |
| Permission error | Workflow needs elevated permissions | Add permissions block |
| Path mismatch | Consumer has different structure | Add conditional in workflow |
| Mypy/lint failure | New code introduced type issues | Fix types or add to ignore |

## Key Principle

**Fail fast on one repo, not on all repos.**

The cost of debugging one failing PR is much lower than debugging 4+ identical failures across all consumers.
