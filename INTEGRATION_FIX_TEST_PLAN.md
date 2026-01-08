# Integration CI Fix - Test Plan

## Problem Summary
Integration Tests CI failing with dependency conflict:
- `requirements.lock`: `ruff==0.14.10`
- `autofix-versions.env`: `RUFF_VERSION=0.14.11`
- Result: Unsatisfiable dependencies

## Solution
Updated `maint-69-sync-integration-repo.yml` to regenerate `requirements.lock` when syncing `autofix-versions.env`.

## Test Plan

### Pre-Merge Testing

1. **Workflow Syntax Validation** ✅
   ```bash
   python3 scripts/validate_workflow_yaml.py .github/workflows/maint-69-sync-integration-repo.yml
   ```
   - Status: PASSED

2. **Local uv Compile Test** ✅
   - Created test pyproject.toml with old ruff version
   - Generated lock file with `ruff==0.14.10`
   - Updated to flexible version constraint
   - Regenerated with `--upgrade`: Got `ruff==0.14.11`
   - Status: PASSED

3. **Code Review** ✅
   - Addressed parameter ordering to match existing format
   - Verified flag consistency with Integration Tests repo
   - Status: PASSED

### Post-Merge Testing

4. **Trigger Sync Workflow**
   ```bash
   # After PR is merged to main
   gh workflow run maint-69-sync-integration-repo.yml --ref main
   ```

5. **Verify Sync Changes**
   ```bash
   # Check that sync created a commit in Integration Tests repo
   gh api repos/stranske/Workflows-Integration-Tests/commits \
     --jq '.[0] | {message: .commit.message, author: .commit.author.name, sha: .sha}'
   
   # Expected commit message should include:
   # - "sync: Update workflow templates from stranske/Workflows"
   # - "requirements.lock (regenerated with updated tool versions)"
   ```

6. **Verify Lock File Update**
   ```bash
   # Check that requirements.lock now has ruff 0.14.11
   gh api repos/stranske/Workflows-Integration-Tests/contents/requirements.lock \
     --jq '.content' | base64 -d | grep "ruff=="
   
   # Expected: ruff==0.14.11
   ```

7. **Monitor Integration Tests CI**
   - Wait for CI to run automatically after sync push
   - Check workflow run status:
     ```bash
     gh run list --repo stranske/Workflows-Integration-Tests --limit 1
     ```
   - Expected: All jobs should pass (conclusion: success)

8. **Verify Job Success**
   ```bash
   # Get latest run ID
   RUN_ID=$(gh run list --repo stranske/Workflows-Integration-Tests \
     --limit 1 --json databaseId --jq '.[0].databaseId')
   
   # Check job statuses
   gh run view $RUN_ID --repo stranske/Workflows-Integration-Tests
   ```
   - Expected: All lint/format/test jobs pass
   - Expected: No dependency resolution errors

9. **Close Issue**
   ```bash
   # If all tests pass, close the issue
   gh issue close <ISSUE_NUMBER> --repo stranske/Workflows \
     --comment "Fixed in PR #<PR_NUMBER>. Integration Tests now pass successfully."
   ```

## Success Criteria

- ✅ Workflow passes validation
- ✅ Code review feedback addressed
- ⏳ Sync workflow successfully pushes to Integration Tests repo
- ⏳ Requirements.lock updated with ruff 0.14.11
- ⏳ Integration Tests CI passes without dependency conflicts
- ⏳ Issue closed

## Rollback Plan

If the fix doesn't work:

1. **Revert the sync commit in Integration Tests repo:**
   ```bash
   cd /tmp/integration-tests
   git clone https://github.com/stranske/Workflows-Integration-Tests.git .
   git revert HEAD
   git push
   ```

2. **Investigate the failure:**
   - Check workflow run logs
   - Verify uv version compatibility
   - Check pyproject.toml structure

3. **Alternative fix:**
   - Manually update requirements.lock in Integration Tests repo
   - Create PR with updated lock file
   - Investigate why sync workflow failed

## Notes

- The fix aligns with the existing lock file format used in Integration Tests
- The `--upgrade` flag is critical to resolve to latest versions
- The workflow uses the same parameter order as the existing lock file header
- This fix will prevent future version conflicts when autofix-versions.env is updated
