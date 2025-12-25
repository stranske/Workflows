# Workflow Audit Report - December 25, 2025

This document provides a comprehensive audit of all GitHub Actions workflows in the Workflows repository, including run statistics, failure analysis, and recommendations.

## Executive Summary

| Category | Count |
|----------|-------|
| Total Workflows | 50 |
| Healthy (>80% success rate) | 17 |
| Needs Attention (50-80% success) | 3 |
| Failing (<50% success) | 3 |
| Never Run / Reusable-only | 8 |
| Archival Candidates | 3 |

## Workflow Run Statistics (Last 30 Days)

### Healthy Workflows (>80% Success Rate)

| Workflow | Total Runs | Success | Failure | Rate | Status |
|----------|-----------|---------|---------|------|--------|
| Agents 70 Orchestrator | 71 | 62 | 0 | 87.3% | ✅ Working |
| Agents Autofix Loop | 43 | 36 | 3 | 83.7% | ✅ Working |
| Agents Debug Issue Event | 4 | 4 | 0 | 100% | ✅ Working |
| Agents Keepalive Loop | 49 | 43 | 0 | 87.8% | ✅ Working |
| Agents Moderate Connector Comments | 8 | 8 | 0 | 100% | ✅ Working |
| Agents PR meta manager | 314 | 303 | 0 | 96.5% | ✅ Working |
| Agents Verifier | 15 | 15 | 0 | 100% | ✅ Working |
| Copilot code review | 8 | 8 | 0 | 100% | ✅ Working |
| Copilot coding agent | 1 | 1 | 0 | 100% | ✅ Working |
| Health 44 Gate Branch Protection | 41 | 36 | 0 | 87.8% | ✅ Working |
| Health 45 Agents Guard | 47 | 38 | 0 | 80.9% | ✅ Working |
| Health 46 Codex Auth Check | 2 | 2 | 0 | 100% | ✅ Working |
| Health 50 Security Scan | 50 | 45 | 0 | 90.0% | ✅ Working |
| Maint 46 Post CI | 44 | 44 | 0 | 100% | ✅ Working |
| Maint 52 Validate Workflows | 50 | 45 | 0 | 90.0% | ✅ Working |
| Maint 60 Release | 2 | 2 | 0 | 100% | ✅ Working |
| Maint 61 Create Floating v1 Tag | 5 | 4 | 1 | 80% | ✅ Working |

### Workflows Needing Attention (50-80% Success Rate)

| Workflow | Total Runs | Success | Failure | Rate | Issue |
|----------|-----------|---------|---------|------|-------|
| CI Autofix Loop | 47 | 37 | 0 | 78.7% | Some action_required |
| Health 40 Sweep | 46 | 36 | 5 | 78.3% | Permission issues |
| PR 11 - Minimal invariant CI | 50 | 40 | 5 | 80.0% | Expected test failures |

### Failing Workflows (<50% Success Rate)

| Workflow | Total Runs | Success | Failure | Rate | Root Cause |
|----------|-----------|---------|---------|------|------------|
| Maint 63 Ensure Agent Environments | 9 | 0 | 9 | 0% | **403 Permission Error** - GITHUB_TOKEN lacks environment management permissions |
| Gate | 47 | 22 | 3 | 46.8% | Intermittent cancellations, not failures |
| Agents 63 Issue Intake | 4 | 2 | 1 | 50% | Expected - triggers on specific events |

## Workflows Never Run in 30 Days

### Reusable Workflows (workflow_call only)

These workflows are designed to be called by other workflows and are not expected to run independently:

| Workflow | Purpose |
|----------|---------|
| agents-64-verify-agent-assignment.yml | Reusable agent assignment verification |
| agents-71-codex-belt-dispatcher.yml | Reusable Codex belt dispatch |
| agents-72-codex-belt-worker.yml | Reusable Codex belt worker |
| agents-73-codex-belt-conveyor.yml | Reusable Codex belt conveyor |
| health-42-actionlint.yml | Reusable actionlint (called by health-40-sweep) |
| reusable-*.yml (10 files) | Various reusable workflows |

### Scheduled/On-Demand Workflows

| Workflow | Trigger | Last Run | Status |
|----------|---------|----------|--------|
| agents-weekly-metrics.yml | Weekly (Mon 6am) | Never | ⚠️ May need validation |
| maint-45-cosmetic-repair.yml | Manual dispatch | Never | ✅ On-demand utility |
| maint-47-disable-legacy-workflows.yml | Manual dispatch | Never | ✅ On-demand utility |

## Consistently Failing Workflows - Root Cause Analysis

### 1. Maint 63 Ensure Agent Environments (100% Failure)

**Error**: `RequestError [HttpError]: Resource not accessible by integration`

**Root Cause**: The workflow attempts to create/update GitHub environments using `github.rest.repos.createOrUpdateEnvironment()`, but the GITHUB_TOKEN does not have sufficient permissions. Environment management requires admin-level access that personal access tokens can provide, but the built-in GITHUB_TOKEN cannot.

**Options**:
1. **Archive** - If environments are already configured manually
2. **Fix** - Use a PAT with admin:repo scope (security consideration)
3. **Keep as Warning** - Run but allow failure for diagnostic purposes

**Recommendation**: Archive - environments can be managed manually and this workflow failing on every push adds noise.

### 2. Maint Coverage Guard (100% Failure)

**Error**: `python: can't open file '/home/runner/work/Workflows/Workflows/tools/coverage_guard.py': [Errno 2] No such file or directory`

**Root Cause**: The `tools/coverage_guard.py` script referenced in the workflow does not exist.

**Recommendation**: Either create the missing script or archive the workflow until needed.

### 3. Selftest Reusable CI (100% Failure)

**Error**: Artifact naming mismatch between expected and actual coverage artifacts

**Root Cause**: The selftest is detecting drift between expected artifact names (`sf-*-coverage-3.11`) and actual (`sf-*-coverage-3.11-1`). This appears to be a test configuration issue.

**Recommendation**: Fix the artifact naming expectations or update the reusable workflow to match.

### 4. Health 40 Sweep (Partial Failures)

**Error**: `403 - Resource not accessible by personal access token` when enforcing branch protection

**Root Cause**: Branch protection enforcement requires admin permissions that the GITHUB_TOKEN doesn't have.

**Recommendation**: The workflow should gracefully handle this by making enforcement optional or using a PAT.

### 5. Health 40/41 Repo Selfcheck/Health (Failures)

**Same root cause as above** - branch protection enforcement permission issues.

## Archival Recommendations

### Immediate Archival Candidates

| Workflow | Reason | Action |
|----------|--------|--------|
| maint-63-ensure-environments.yml | 100% failure rate, cannot work with GITHUB_TOKEN | Move to archived/ |
| maint-coverage-guard.yml | Missing required script, 100% failure | Move to archived/ |
| maint-51-dependency-refresh.yml.disabled | Already disabled | Delete or move to archived/ |

### Consider for Archival

| Workflow | Reason | Decision Needed |
|----------|--------|-----------------|
| agents-weekly-metrics.yml | Never run, metrics aggregation may not be needed | Review purpose |
| selftest-reusable-ci.yml | Consistent failures, may need significant fixes | Fix or archive |

## Optimization Opportunities

### 1. Parallel Execution

Several workflows could benefit from running jobs in parallel:
- `health-40-sweep.yml` - actionlint and branch-protection-verify could run in parallel
- `selftest-ci.yml` - test matrix could be expanded for parallel runs

### 2. Conditional Execution

- Skip branch protection enforcement steps when running without admin token
- Add early exit conditions when prerequisites aren't met

### 3. Caching Improvements

- Python dependency caching could be added to more workflows
- Action version caching is already in place for actionlint

## Recommended Actions

### Priority 1: Fix Immediately

1. Archive `maint-63-ensure-environments.yml`
2. Archive `maint-coverage-guard.yml`
3. Clean up `maint-51-dependency-refresh.yml.disabled`

### Priority 2: Fix Soon

1. Update `health-40-sweep.yml` to make enforcement optional
2. Fix `selftest-reusable-ci.yml` artifact naming
3. Validate `agents-weekly-metrics.yml` works as expected

### Priority 3: Monitor

1. Gate workflow cancellations (normal behavior)
2. PR 11 test failures (may be expected)

---

*Generated on December 25, 2025*
