# Integration Test CI Failure Fix (Run 61)

## Problem Summary

The Workflows-Integration-Tests CI run 61 failed due to a Black formatting issue in `scripts/validate_dependency_test_setup.py`.

**Failed Run:** [20908213080](https://github.com/stranske/Workflows-Integration-Tests/actions/runs/20908213080)

**Error:**
```
would reformat /home/runner/work/Workflows-Integration-Tests/Workflows-Integration-Tests/scripts/validate_dependency_test_setup.py
Oh no! 💥 💔 💥
1 file would be reformatted, 10 files would be left unchanged.
```

## Root Cause Analysis

### Issue
The `scripts/validate_dependency_test_setup.py` file existed in both repositories:
- **Workflows repo**: Correctly formatted (passes Black with line-length=100)
- **Integration-Tests repo**: Outdated version with formatting issues

### Formatting Differences
The Integration-Tests version had:
- Single quotes instead of double quotes
- Long lines not wrapped properly
- Missing spacing around operators

### Why It Happened
The file was **not included in the sync templates**, so changes in the Workflows repo didn't propagate to Integration-Tests, causing the two versions to diverge.

## Solution Implemented

### 1. Added File to Templates
Copied the correctly formatted `validate_dependency_test_setup.py` from `scripts/` to `templates/integration-repo/scripts/`:

```bash
cp scripts/validate_dependency_test_setup.py \
   templates/integration-repo/scripts/validate_dependency_test_setup.py
```

### 2. Updated Sync Workflow
Modified `.github/workflows/maint-69-sync-integration-repo.yml` to sync the scripts directory:

```yaml
# Sync scripts directory (if exists in templates)
if [ -d "../workflows/templates/integration-repo/scripts" ]; then
  mkdir -p scripts
  cp -r "../workflows/templates/integration-repo/scripts/"* scripts/
  echo "✅ Synced scripts directory from templates"
fi
```

### 3. Updated Git Commit
Updated the sync workflow to include scripts in the git add command:

```bash
git add .github/workflows/ requirements.lock scripts/
```

## How to Apply the Fix

### Option 1: Wait for Automatic Sync (Recommended)
When this PR is merged to main:
1. The `maint-69-sync-integration-repo.yml` workflow will trigger automatically
2. It will push the correctly formatted file to Integration-Tests
3. The next CI run in Integration-Tests will pass

### Option 2: Manual Sync (Immediate Fix)
To apply the fix immediately before PR merge:

```bash
# From the Workflows repository
./scripts/trigger-integration-sync.sh

# Or using gh CLI directly
gh workflow run maint-69-sync-integration-repo.yml \
  --repo stranske/Workflows \
  --ref main
```

### Option 3: Auto-Fix Workflow (Already Available)
The `maint-71-auto-fix-integration.yml` workflow should have auto-fixed this, but it may not have triggered. If needed, manually trigger it:

```bash
gh workflow run maint-71-auto-fix-integration.yml \
  --repo stranske/Workflows \
  --ref main \
  -f run_id=20908213080
```

## Verification Steps

After the sync completes:

1. **Check the Integration-Tests repo:**
   ```bash
   # View the file in Integration-Tests
   gh api repos/stranske/Workflows-Integration-Tests/contents/scripts/validate_dependency_test_setup.py \
     --jq '.content' | base64 -d | head -30
   ```

2. **Verify formatting:**
   ```bash
   # Should show: "All done! ✨ 🍰 ✨"
   black --check --line-length 100 scripts/validate_dependency_test_setup.py
   ```

3. **Run CI manually:**
   ```bash
   # Trigger CI in Integration-Tests
   gh workflow run ci.yml --repo stranske/Workflows-Integration-Tests
   ```

## Prevention

This fix ensures future divergence is prevented:

1. ✅ File is now in `templates/integration-repo/scripts/`
2. ✅ Sync workflow automatically copies templates on changes
3. ✅ Trigger path includes `templates/integration-repo/**`
4. ✅ Both repos will stay in sync

## Files Changed

- `templates/integration-repo/scripts/validate_dependency_test_setup.py` (new file)
- `.github/workflows/maint-69-sync-integration-repo.yml` (updated)
- `scripts/trigger-integration-sync.sh` (new helper script)

## References

- Issue: [Integration CI failed (run 61)]
- Failed Run: https://github.com/stranske/Workflows-Integration-Tests/actions/runs/20908213080
- Sync Workflow: `.github/workflows/maint-69-sync-integration-repo.yml`
- Auto-Fix Workflow: `.github/workflows/maint-71-auto-fix-integration.yml`
