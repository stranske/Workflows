# Integration Test Run 60 - Formatting Failure Fix

## Problem Summary

Integration CI run 60 failed on 2026-01-11 due to black formatting issues in `scripts/validate_dependency_test_setup.py`.

**Failed Run:** https://github.com/stranske/Workflows-Integration-Tests/actions/runs/20889541321

**Root Cause:** The file was manually added to Integration-Tests repo on 2026-01-05 (commit 90e6912f) with formatting that doesn't match the black configuration (line-length=100).

## Fix Applied in Workflows Repo

### 1. Fixed Autofix Workflow (maint-71)

**File:** `.github/workflows/maint-71-auto-fix-integration.yml`

**Issue:** jq syntax error when extracting run ID from issue body

**Fix:** Changed line 42 from `capture("runs/(?<id>[0-9]+)")?.id` to `capture("runs/(?<id>[0-9]+)") | .id`

The optional chaining operator doesn't work with nested field access in jq. Split into two operations.

## Solution Options for Integration-Tests

### Option A: Re-trigger Autofix Workflow (RECOMMENDED)

Comment on the Integration CI failure issue to re-trigger the autofix workflow.

### Option B: Manual Trigger

```bash
gh workflow run maint-70-fix-integration-formatting.yml \
  --repo stranske/Workflows --ref main
```

### Option C: Apply Fix Directly

```bash
git clone https://github.com/stranske/Workflows-Integration-Tests.git
cd Workflows-Integration-Tests
black --line-length 100 scripts/validate_dependency_test_setup.py
git add scripts/validate_dependency_test_setup.py
git commit -m "fix: Auto-format validate_dependency_test_setup.py"
git push origin main
```

## Verification

Verify CI passes at: https://github.com/stranske/Workflows-Integration-Tests/actions
