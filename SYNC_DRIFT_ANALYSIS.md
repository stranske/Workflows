# Integration-Tests Sync Drift Analysis

## Issue Summary
The health-67-integration-sync-check.yml workflow detected drift between the Workflows-Integration-Tests repository and the templates in templates/integration-repo/.

## Drift Details

### autofix-versions.env
Integration-Tests has older versions compared to the canonical .github/workflows/autofix-versions.env:

| Tool | Integration-Tests | Canonical | Status |
|------|-------------------|-----------|--------|
| BLACK_VERSION | 25.11.0 | 25.12.0 | Needs update |
| RUFF_VERSION | 0.14.7 | 0.14.10 | Needs update |
| MYPY_VERSION | 1.19.0 | 1.19.1 | Needs update |
| PYTEST_VERSION | 9.0.1 | 9.0.2 | Needs update |
| COVERAGE_VERSION | 7.12.0 | 7.13.1 | Needs update |
| JSONSCHEMA_VERSION | 4.23.0 | 4.22.0 | Needs downgrade (compatibility) |

### Templates Status
✅ templates/integration-repo/.github/workflows/autofix-versions.env is **in sync** with canonical
✅ templates/integration-repo/.github/workflows/ci.yml has correct __WORKFLOW_REF__ placeholder

## Root Cause
The maint-69-sync-integration-repo.yml workflow is designed to automatically sync these changes to Integration-Tests, but it has been **failing** on every run:

- Run 20577503495 (2025-12-29 16:22) - failure
- Run 20565466898 (2025-12-29 05:15) - failure
- Run 20562075978 (2025-12-29 00:54) - failure
- Run 20535987024 (2025-12-27 07:17) - failure
- Run 20523758230 (2025-12-26 14:07) - failure

The workflow requires either `CODESPACES_WORKFLOWS` or `SERVICE_BOT_PAT` secret to push changes to the Integration-Tests repo (see line 43-51, 60 of maint-69-sync-integration-repo.yml).

## Resolution Options

### Option 1: Fix Sync Workflow Credentials (Recommended)
1. Verify `CODESPACES_WORKFLOWS` or `SERVICE_BOT_PAT` secret exists and has valid credentials
2. Ensure the token has write permissions to stranske/Workflows-Integration-Tests
3. Manually trigger maint-69-sync-integration-repo.yml via workflow_dispatch
4. Verify the sync completes successfully

### Option 2: Manual Sync
1. Clone Workflows-Integration-Tests locally
2. Copy .github/workflows/autofix-versions.env from this repo
3. Commit and push changes
4. Close drift issue

## Recommendation
Fix the credentials (Option 1) to enable automated syncing for future changes. The sync infrastructure is already in place and working correctly - it just needs valid credentials.
