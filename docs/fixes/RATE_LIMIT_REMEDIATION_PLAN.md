# Rate Limit Comprehensive Remediation Plan

> **Created:** 2026-02-02  
> **Status:** 🔴 Active — Implementation in Progress  
> **PR:** This document tracks work in PR #TBD  
> **Goal:** Multiple PRs running simultaneously without rate limit failures

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Current State Analysis](#current-state-analysis)
3. [Complete PR History](#complete-pr-history)
4. [Root Cause Analysis](#root-cause-analysis)
5. [Implementation Plan](#implementation-plan)
6. [Success Criteria](#success-criteria)
7. [Testing Strategy](#testing-strategy)
8. [Handoff Protocol](#handoff-protocol)

---

## Executive Summary

### The Problem
Despite 40+ PRs attempting to fix API rate limiting, PRs #4647, #4648, and #4641 in Trend_Model_Project still grind to a halt. The keepalive summary falsely shows "🔄 Agent Running" when the agent is actually blocked by rate limits.

### Root Cause
The token load balancer infrastructure exists but fails to initialize properly in many job contexts due to:
1. Missing `@octokit/rest` dependency in consumer repos
2. Secrets not propagating to all workflow jobs
3. No unified dependency management strategy
4. Inconsistent application of the load balancer across workflows

### Solution
A comprehensive, sustainable fix that:
1. **Centralizes** dependency management via a reusable setup action
2. **Ensures** consistent token availability across ALL jobs
3. **Implements** accurate status reporting when rate-limited
4. **Verifies** actual token switching through integration tests

---

## Current State Analysis

### Token Pool Capacity (Theoretical)
| Token | Pool Size | Account/App | Status |
|-------|-----------|-------------|--------|
| WORKFLOWS_APP | 5,000/hr | GitHub App | ✅ Available |
| KEEPALIVE_APP | 5,000/hr | GitHub App | ✅ Available |
| GH_APP | 5,000/hr | GitHub App | ⚠️ Not configured |
| SERVICE_BOT_PAT | 5,000/hr | stranske-automation-bot | ✅ Available |
| CODESPACES_WORKFLOWS | 5,000/hr | stranske | ✅ Available |
| OWNER_PR_PAT | 5,000/hr | stranske | ✅ Available |
| **Total Theoretical** | **30,000/hr** | | |

### Actual Observed Behavior (Run 21563133208)
```
12:47:24 - Evaluate keepalive loop: Token registry initialized with 7 tokens ✅
12:47:42 - Mark agent running: Token registry initialized with 0 tokens ❌
12:54:47 - Codex job: Token registry initialized with 1 token (GITHUB_TOKEN only) ❌
12:55:31 - Update summary: Token registry initialized with 0 tokens ❌
```

### Health-75 Diagnostic Status
The API rate diagnostic workflow itself is **failing** due to the same issues:
- Last 5 runs: ALL FAILURES
- Export load balancer step shows empty strings for all secrets
- Retry helpers can't initialize without @octokit/rest

---

## Complete PR History

### Phase 1: Foundation (Jan 21-22, 2026)

#### PR #1008: feat: Add dynamic token load balancer for API rate limit management
**Merged:** 2026-01-21T07:07:38Z
**Impact:** ⭐⭐⭐⭐⭐ Core architecture

Created the token load balancer (`token_load_balancer.js`) with:
- Multi-token registry (PATs + Apps)
- Capacity-based token selection
- Token specialization for exclusive tasks
- Rate limit checking via API headers

**Limitation:** Required `@octokit/rest` but didn't establish installation pattern.

#### PR #1013: feat: add rate limit notification and label sync for agent keepalive
**Merged:** 2026-01-21T15:09:07Z
**Impact:** ⭐⭐⭐

Added `agent:rate-limited` label mechanism and notification system.

**Limitation:** Only notifies; doesn't prevent work stoppage.

#### PR #1014: fix: improve rate limit handling in agent:retry label handler
**Merged:** 2026-01-21T17:55:59Z
**Impact:** ⭐⭐

Improved retry behavior when `agent:retry` label is applied.

**Limitation:** Manual intervention still required.

#### PR #1028: Fix/keepalive status and restart instructions
**Merged:** 2026-01-22T03:21:25Z
**Impact:** ⭐⭐

Better error messages and restart guidance.

**Limitation:** Documentation only; no code fix.

### Phase 2: Retry Wrapper Integration (Jan 22-23, 2026)

#### PR #1051: Add retry wrappers to agents autofix loop
**Merged:** 2026-01-22T19:14:34Z
**Impact:** ⭐⭐⭐

Wrapped autofix-loop API calls with `createTokenAwareRetry()`.

**Problem:** Assumed @octokit would be available.

#### PR #1052: Add retry wrapper to belt dispatcher
**Merged:** 2026-01-22T22:14:41Z
**Impact:** ⭐⭐⭐

Added retry wrapper to codex belt dispatcher.

**Problem:** Same dependency assumption.

#### PR #1077: Wrap autofix-loop API calls with retries
**Merged:** 2026-01-23T06:53:59Z
**Impact:** ⭐⭐⭐

Extended retry coverage in autofix workflows.

**Problem:** Pattern not applied consistently.

#### PR #1079: Integrate retry helpers in keepalive loop
**Merged:** 2026-01-23T07:10:37Z
**Impact:** ⭐⭐⭐⭐

Critical integration of retry helpers into the keepalive loop.

**Problem:** Didn't ensure deps installed in all job contexts.

#### PR #1080: Integrate retry helpers in reusable codex run
**Merged:** 2026-01-23T07:25:44Z
**Impact:** ⭐⭐⭐⭐

Added retry helpers to the reusable codex run workflow.

**Problem:** Same dependency gap.

#### PR #1082: fix: sync api-rate-limit helpers to consumer workflows
**Merged:** 2026-01-23T18:24:28Z
**Impact:** ⭐⭐⭐

Synced retry helpers to consumer repo templates.

**Problem:** Synced code but not dependency installation.

### Phase 3: Diagnostic Infrastructure (Jan 26-27, 2026)

#### PR #1126: issue-4558 fix: stabilize api rate diagnostic
**Merged:** 2026-01-27T06:36:30Z
**Impact:** ⭐⭐

First attempt to fix Health-75 diagnostic workflow.

**Problem:** Incomplete fix, workflow still failing.

#### PR #1127: issue-4558 fix: stabilize api rate diagnostic
**Merged:** 2026-01-27T06:52:35Z
**Impact:** ⭐⭐

Continued diagnostic fixes.

**Problem:** Still not working.

#### PR #1128: issue-4558 fix: use pat for historical runs
**Merged:** 2026-01-27T06:59:01Z
**Impact:** ⭐⭐

Added PAT fallback for historical run queries.

**Problem:** Partial fix only.

#### PR #1130: fix: token fallback for Health 75 historical runs
**Merged:** 2026-01-27T07:18:14Z
**Impact:** ⭐⭐

Enhanced token fallback chain.

**Problem:** Fallback still fails without deps.

#### PR #1132: fix: use workflows app token for Health 75 history
**Merged:** 2026-01-27T07:37:22Z
**Impact:** ⭐⭐

Switched to WORKFLOWS_APP for diagnostics.

**Problem:** App token minting requires deps.

#### PR #1133: feat: add actions access diagnostics
**Merged:** 2026-01-27T08:00:28Z
**Impact:** ⭐⭐

Added action access verification.

**Status:** Observability improvement.

#### PR #1134: fix(health-75): use query param instead of -F for GET request
**Merged:** 2026-01-27T08:32:53Z
**Impact:** ⭐

Fixed gh CLI syntax issue.

**Status:** Minor fix.

#### PR #1135: fix: add rate-limit-aware retry to high-frequency scripts
**Merged:** 2026-01-27T09:59:32Z
**Impact:** ⭐⭐⭐

Added retry wrappers to more scripts.

**Problem:** Pattern spread without dep management.

#### PR #1139: fix(#1136): add paginate.iterator support to rate-limit wrapper
**Merged:** 2026-01-27T10:46:41Z
**Impact:** ⭐⭐⭐

Fixed pagination support in retry wrapper.

**Status:** Good enhancement.

### Phase 4: Load Balancer Expansion (Jan 28-31, 2026)

#### PR #1142: feat: standardize token export for retry helpers
**Merged:** 2026-01-28T20:08:23Z
**Impact:** ⭐⭐⭐⭐

Standardized how tokens are exported to environment.

**Problem:** Not applied everywhere.

#### PR #1146: feat: verify token load sharing
**Merged:** 2026-01-29T06:29:51Z
**Impact:** ⭐⭐⭐

Added verification that load sharing actually works.

**Status:** Good testing infrastructure.

#### PR #1147: fix: install octokit deps for load-sharing check
**Merged:** 2026-01-29T06:42:25Z
**Impact:** ⭐⭐

First explicit acknowledgment of the dependency problem.

**Problem:** Only fixed one location.

#### PR #1148: Sync export-load-balancer-tokens action to consumer repos
**Merged:** 2026-01-31T07:26:48Z
**Impact:** ⭐⭐⭐⭐

Synced the load balancer action to consumer repos.

**Problem:** Action exists but not called consistently.

#### PR #1152: chore: run api rate diagnostic every 30 minutes
**Merged:** 2026-01-30T17:39:41Z
**Impact:** ⭐⭐

Increased diagnostic frequency.

**Status:** Observability improvement.

#### PR #1161: fix: stabilize keepalive load balancing
**Merged:** 2026-01-31T05:41:08Z
**Impact:** ⭐⭐⭐

Attempted to stabilize the keepalive load balancer.

**Problem:** Incomplete coverage.

#### PR #1162: fix: export load balancer tokens in keepalive
**Merged:** 2026-01-31T05:51:00Z
**Impact:** ⭐⭐⭐

Added export step to keepalive workflow.

**Problem:** Not all jobs covered.

#### PR #1170: fix(keepalive): install octokit deps
**Merged:** 2026-01-31T17:10:21Z
**Impact:** ⭐⭐⭐

Explicit npm install for keepalive workflow.

**Problem:** Ad-hoc; not sustainable.

### Phase 5: Remediation Attempts (Feb 1-2, 2026)

#### PR #1171: fix(pr-meta): use load balancer for Workflows ref
**Merged:** 2026-01-31T23:52:37Z
**Impact:** ⭐⭐

Extended load balancer to PR meta workflow.

**Problem:** Still failing.

#### PR #1172: fix: expand load balancer coverage
**Merged:** 2026-02-01T02:24:36Z
**Impact:** ⭐⭐⭐

Broader expansion of load balancer.

**Problem:** Incomplete.

#### PR #1173: fix: add token-aware retry to issue workflows
**Merged:** 2026-02-01T03:25:30Z
**Impact:** ⭐⭐⭐

Added retry to issue-related workflows.

**Problem:** Still failing.

#### PR #1177: Fix/retry wrapper remediation
**Merged:** 2026-02-01T07:31:40Z
**Impact:** ⭐⭐

Attempted to fix retry wrapper issues.

**Problem:** Didn't solve root cause.

#### PR #1179: Fix/retry wrapper remediation
**Merged:** 2026-02-01T08:04:36Z
**Impact:** ⭐⭐

Continued remediation attempts.

**Problem:** Still failing.

#### PR #1181: fix: export load balancer tokens before retry
**Merged:** 2026-02-01T11:13:33Z
**Impact:** ⭐⭐⭐

Ensured tokens exported before retry attempts.

**Problem:** Not all jobs.

#### PR #1182: fix: install octokit deps where required
**Merged:** 2026-02-01T12:06:30Z
**Impact:** ⭐⭐⭐

Latest attempt to fix dependency issue.

**Result:** PRs #4647, #4648, #4641 STILL FAILING as of Feb 2.

---

## Root Cause Analysis

### Why 40+ PRs Haven't Fixed This

1. **No Unified Dependency Strategy**
   - Each fix adds `npm install` to specific locations
   - No enforcement that new workflows include it
   - Version drift possible across locations

2. **Inconsistent Application**
   - Some jobs get load balancer, others don't
   - Secrets passed to some jobs, not others
   - Pattern not documented as requirement

3. **Inadequate Testing**
   - Fixes verified by "does workflow run" not "does it actually switch tokens"
   - No integration test that exhausts one pool and verifies switch
   - Consumer repo testing neglected

4. **Status Reporting Lies**
   - "🔄 Agent Running" shown when agent is blocked
   - No indication of which token pools are exhausted
   - No information about when capacity returns

### The Fundamental Gap

```
BEFORE (Current - Broken):
┌─────────────────────────────────────────────────────────────┐
│  Job A: "Evaluate"           Job B: "Mark Running"          │
│  ┌─────────────────┐         ┌─────────────────┐           │
│  │ Checkout        │         │ Checkout        │           │
│  │ Export Tokens ✅ │         │ (no export) ❌   │           │
│  │ npm install ✅   │         │ (no npm) ❌      │           │
│  │ Load Balancer ✅ │         │ GITHUB_TOKEN ❌  │           │
│  └─────────────────┘         └─────────────────┘           │
│        Works                      Fails                     │
└─────────────────────────────────────────────────────────────┘

AFTER (Proposed - Fixed):
┌─────────────────────────────────────────────────────────────┐
│  ALL JOBS use:                                              │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ - uses: ./.github/actions/setup-api-client              ││
│  │   with:                                                 ││
│  │     secrets: ${{ toJSON(secrets) }}                     ││
│  │   # Single action that:                                 ││
│  │   # 1. Installs @octokit/* at pinned versions           ││
│  │   # 2. Exports all available tokens                     ││
│  │   # 3. Initializes load balancer                        ││
│  └─────────────────────────────────────────────────────────┘│
│        Consistent across all jobs                           │
└─────────────────────────────────────────────────────────────┘
```

---

## Implementation Plan

### Phase A: Create Unified Setup Action (Priority: Critical)

**Goal:** Single reusable action that handles all API client setup

#### Task A.1: Create `.github/actions/setup-api-client/action.yml` ✅ DONE

**Note:** The actual implementation installs 4 packages and handles jq availability. See the full action at `.github/actions/setup-api-client/action.yml`.

Usage example:
```yaml
- uses: ./.github/actions/setup-api-client
  with:
    secrets: ${{ toJSON(secrets) }}
    github_token: ${{ secrets.GITHUB_TOKEN }}
```

#### Task A.2: Version pinning ✅ DONE

Version pinning is done inline in the npm install command (no separate package.json needed):
```bash
npm install --no-save \
  @octokit/rest@20.0.2 \
  @octokit/plugin-retry@6.0.1 \
  @octokit/plugin-paginate-rest@9.1.5 \
  @octokit/auth-app@6.0.3
```

#### Task A.3: Update sync manifest to include the action

### Phase B: Apply to High-Frequency Workflows (Priority: Critical)

Update these workflows to use the new action:

1. `agents-keepalive-loop.yml` - ALL jobs
2. `reusable-codex-run.yml` - ALL jobs  
3. `agents-autofix-loop.yml` - ALL jobs
4. `agents-70-orchestrator.yml` - ALL jobs
5. `reusable-70-orchestrator-main.yml` - ALL jobs

### Phase C: Fix Status Reporting (Priority: High)

#### Task C.1: Update keepalive state reporting

Replace:
```
🔄 Agent Running
```

With when rate-limited:
```
🛑 Agent Stopped: API capacity depleted

| Token | Remaining | Reset |
|-------|-----------|-------|
| WORKFLOWS_APP | 0 | 13:30 UTC |
| KEEPALIVE_APP | 23 | 13:45 UTC |
| SERVICE_BOT_PAT | 0 | 13:30 UTC |
| CODESPACES | 1,247 | 14:00 UTC |

**Action:** Waiting for rate limits to reset. Next attempt at 13:30 UTC.
```

#### Task C.2: Add rate limit status to PR summary

### Phase D: Consumer Repo Sync (Priority: High)

1. Add `setup-api-client` action to sync manifest
2. Update consumer repo templates
3. Trigger sync workflow

### Phase E: Integration Testing (Priority: High)

#### Task E.1: Create test workflow that verifies token switching

```yaml
# health-76-token-switching-test.yml
# Runs on-demand to verify load balancer actually switches tokens
```

#### Task E.2: Add verbose logging (failure-only)

Only log token selection details when an API call fails.

### Phase F: Maintenance Workflows (Priority: Medium)

Apply setup action to less frequent workflows:
- `health-*.yml` workflows
- `maint-*.yml` workflows

---

## Success Criteria

### Must Have (Blocking)
- [ ] Token registry initializes with 5+ tokens in ALL jobs
- [ ] No `@octokit/rest` import errors in any context
- [ ] Multiple PRs (#4647 style) run simultaneously without rate limit failures
- [ ] Status shows "🛑 Agent Stopped" when rate-limited, not "🔄 Running"
- [ ] Integration test confirms actual token switching

### Should Have
- [ ] Health-75 diagnostic workflow passes consistently
- [ ] Consumer repos inherit setup action via sync
- [ ] Verbose logging only on failure

### Nice to Have
- [ ] Proactive token switching before exhaustion
- [ ] GraphQL batching for reduced API calls

---

## Testing Strategy

### Test 1: Workflows Repo Verification

1. Create test PR in Workflows repo
2. Add `agent:codex` label
3. Monitor keepalive loop
4. Verify: All jobs show "Token registry initialized with X tokens" where X >= 5

### Test 2: Consumer Repo Verification (Trend_Model_Project)

1. Sync changes to TMP
2. Create test PR with Monte Carlo task
3. Monitor keepalive loop
4. Verify: Same token initialization behavior

### Test 3: Token Switching Verification

1. Run health-76-token-switching-test (to be created)
2. Deliberately exhaust one token pool
3. Verify: System switches to alternate token
4. Verify: Work continues without interruption

### Test 4: Status Reporting Verification

1. Artificially trigger rate limit condition
2. Verify: Summary shows "🛑 Agent Stopped" not "🔄 Running"
3. Verify: Token capacity table displayed

---

## Handoff Protocol

### If This PR Is Not Complete When You Start

1. **Read this document** to understand history and plan
2. **Check the "Implementation Plan" section** for current phase
3. **Run diagnostics:**
   ```bash
   GH_TOKEN=$CODESPACES gh workflow run "Health 75 API Rate Diagnostic" --repo stranske/Workflows
   ```
4. **Check recent keepalive failures:**
   ```bash
   GH_TOKEN=$CODESPACES gh run list --repo stranske/Trend_Model_Project --workflow "Agents Keepalive Loop" --status failure --limit 5
   ```

### Key Files to Know

| File | Purpose |
|------|---------|
| `.github/actions/setup-api-client/action.yml` | Unified setup action (created in this PR) |
| `.github/scripts/token_load_balancer.js` | Core load balancer logic |
| `.github/scripts/github-api-with-retry.js` | Retry wrapper |
| `.github/workflows/agents-keepalive-loop.yml` | Main keepalive workflow |

### Don't Forget

- **Use `CODESPACES` PAT** for cross-repo operations
- **Test in BOTH** Workflows repo AND consumer repo
- **Verify actual switching** not just "tokens available"

---

## Version History

| Date | Change | Author |
|------|--------|--------|
| 2026-02-02 | Initial plan created | Claude |

---

## Remaining Work After PR #1183

### What PR #1183 Accomplishes ✅

1. **Creates `setup-api-client` action** - Unified npm install + token export
2. **Updates `agents-keepalive-loop.yml`** - 4 jobs now use the new action
3. **Syncs to consumer repos** - Both action and workflow are in templates/consumer-repo/

### What Still Needs Fixing ⚠️

The following workflows still use the old `export-load-balancer-tokens` pattern and should be updated:

| Workflow | Priority | Notes |
|----------|----------|-------|
| `agents-autofix-loop.yml` | HIGH | High-frequency, deprecated but still active |
| `agents-auto-pilot.yml` | HIGH | End-to-end orchestrator |
| `agents-71-codex-belt-dispatcher.yml` | MEDIUM | Belt system |
| `agents-72-codex-belt-worker.yml` | MEDIUM | Belt system |
| `agents-73-codex-belt-conveyor.yml` | MEDIUM | Belt system |
| `agents-verifier.yml` | MEDIUM | Verification workflow |
| `agents-verify-to-issue-v2.yml` | LOW | Deprecated |
| `agents-verify-to-new-pr.yml` | LOW | Follow-up creation |
| `maint-coverage-guard.yml` | LOW | Daily monitoring |

### Update Pattern

For each workflow, replace this pattern:
```yaml
- name: Install load balancer dependencies
  run: npm install --no-save --no-package-lock @octokit/rest @octokit/auth-app

- name: Export load balancer tokens
  uses: ./.github/actions/export-load-balancer-tokens
  with:
    github_token: ${{ github.token }}
    service_bot_pat: ${{ secrets.SERVICE_BOT_PAT }}
    # ... many more individual secrets ...
```

With this:
```yaml
- name: Setup API client
  uses: ./.github/actions/setup-api-client
  with:
    secrets: ${{ toJSON(secrets) }}
    github_token: ${{ github.token }}
```

### Template Sync Architecture

**Important**: The sync system copies from `templates/consumer-repo/`, NOT from `.github/workflows/`. 

When updating workflows:
1. Update `.github/workflows/<name>.yml` (for Workflows repo)
2. Copy to `templates/consumer-repo/.github/workflows/<name>.yml` (for sync to consumer repos)
3. Or ensure they match

### Verification After Merge

1. Wait for sync workflow to run (triggered by merge to main)
2. Check TMP has updated files:
   - `.github/actions/setup-api-client/action.yml`
   - `.github/workflows/agents-keepalive-loop.yml`
3. Create a test PR with `agent:codex` label
4. Verify logs show: "Token registry initialized with X tokens" (X >= 5)
