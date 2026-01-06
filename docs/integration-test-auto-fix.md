# Integration Test Auto-Fix Guide

## Overview

When integration tests fail in the `Workflows-Integration-Tests` repository due to formatting issues, we have automated workflows to fix them.

## Problem

Integration tests can fail for various reasons, but commonly they fail due to:
- Black formatting issues
- Ruff lint issues
- File formatting inconsistencies

## Solutions

### 1. Automated Fix (Recommended)

The `maint-71-auto-fix-integration.yml` workflow automatically detects and fixes formatting issues when:
- An issue is created with "Integration CI failed" in the title
- Comments are added to existing integration failure issues
- Manual trigger via workflow_dispatch

#### How it Works

1. **Detection**: Extracts the failed run ID from the issue
2. **Verification**: Checks if the run actually failed
3. **Fix**: Applies Black and Ruff formatting to the Integration-Tests repo
4. **Push**: Commits and pushes the fixes
5. **Notify**: Comments on the issue with results

### 2. Manual Fix

If you need to manually trigger the fix:

```bash
# Via GitHub UI:
# 1. Go to: https://github.com/stranske/Workflows/actions/workflows/maint-70-fix-integration-formatting.yml
# 2. Click "Run workflow"
# 3. Optionally customize the commit message
# 4. Click "Run workflow" button
```

Or use the GitHub CLI:

```bash
gh workflow run maint-70-fix-integration-formatting.yml \
  --repo stranske/Workflows \
  -f commit_message="fix: Auto-format files to meet lint standards"
```

### 3. Local Fix

If you have both repositories cloned locally:

```bash
# Run the fix script
cd /path/to/Workflows
./scripts/fix-integration-tests-formatting.sh /path/to/Workflows-Integration-Tests

# Or manually
cd /path/to/Workflows-Integration-Tests
python3 -m pip install black ruff
black scripts/ tests/ src/
ruff check --fix scripts/ tests/ src/
git add -A
git commit -m "fix: Auto-format files to meet lint standards"
git push
```

## Prevention

### For Integration-Tests Repository

To prevent future formatting issues, add an autofix workflow:

1. Copy `templates/consumer-repo/.github/workflows/autofix.yml` to Integration-Tests
2. Copy `templates/consumer-repo/.github/workflows/autofix-versions.env` to Integration-Tests
3. Commit and push

```bash
cd /path/to/Workflows-Integration-Tests
mkdir -p .github/workflows
cp /path/to/Workflows/templates/consumer-repo/.github/workflows/autofix.yml .github/workflows/
cp /path/to/Workflows/templates/consumer-repo/.github/workflows/autofix-versions.env .github/workflows/
git add .github/workflows/
git commit -m "feat: Add autofix workflow"
git push
```

### Pre-commit Hooks

Add pre-commit hooks to catch issues locally:

```bash
cd /path/to/Workflows-Integration-Tests
pip install pre-commit
pre-commit install
```

Create `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/psf/black
    rev: 25.12.0  # Check for latest: https://github.com/psf/black/releases
    hooks:
      - id: black
        language_version: python3.12
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.14.10  # Check for latest: https://github.com/astral-sh/ruff-pre-commit/releases
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
```

## Troubleshooting

### Workflow Doesn't Trigger

If `maint-71-auto-fix-integration.yml` doesn't auto-trigger:
1. Check that the issue title contains "Integration CI failed"
2. Verify the issue body contains a valid run ID
3. Manually trigger via workflow_dispatch

### Fixes Don't Resolve Issue

If formatting fixes don't resolve the CI failure:
1. Check the actual CI logs for the real error
2. The issue might not be formatting-related
3. Investigate test failures, dependency issues, or other problems

### Permission Errors

If the workflow fails to push:
1. Verify `SERVICE_BOT_PAT` secret is set and valid
2. Check that the PAT has `repo` and `workflow` scopes
3. Ensure the bot has write access to Workflows-Integration-Tests

## Related Files

- Automated workflow: `.github/workflows/maint-71-auto-fix-integration.yml`
- Manual workflow: `.github/workflows/maint-70-fix-integration-formatting.yml`
- Fix script: `scripts/fix-integration-tests-formatting.sh`
- Sync workflow: `.github/workflows/maint-69-sync-integration-repo.yml`

## Examples

### Current Issue (Run #52, #53)

The current failures are due to:
```
would reformat scripts/validate_dependency_test_setup.py
```

**Fix**:
1. Manually trigger `maint-70-fix-integration-formatting.yml`
2. Or wait for `maint-71-auto-fix-integration.yml` to auto-run
3. Verify tests pass after the fix

### Verification

After applying fixes:
1. Go to: https://github.com/stranske/Workflows-Integration-Tests/actions
2. Check that the latest CI run passes
3. Close the issue in Workflows repository
