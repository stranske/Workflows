# Workflow System Bug Report & Improvement Plan

> **Status**: Active evaluation document  
> **Last Updated**: 2025-01-XX  
> **Primary Focus Areas**: API Rate Limiting, Keepalive Iteration Failures, Branch Sync Issues

---

## Executive Summary

This document provides a comprehensive bug analysis of the GitHub Actions workflow system, with particular focus on two critical operational issues:

1. **GitHub API Rate Limiting**: The orchestrator and supporting workflows make excessive API calls, frequently hitting GitHub's rate limits during scheduled runs.

2. **Keepalive Iteration Failures**: The keepalive functionality rarely completes all iterations before encountering branch update conflicts or sync failures.

---

## Table of Contents

1. [Critical Issues](#1-critical-issues)
2. [API Rate Limiting Analysis](#2-api-rate-limiting-analysis)
3. [Keepalive Branch Sync Issues](#3-keepalive-branch-sync-issues)
4. [Workflow-Specific Bugs](#4-workflow-specific-bugs)
5. [Improvement Recommendations](#5-improvement-recommendations)
6. [Implementation Priority](#6-implementation-priority)

---

## 1. Critical Issues

### Issue #1: API Rate Limit Exhaustion

**Severity**: High  
**Impact**: Workflow failures, incomplete keepalive iterations, stalled automation

**Symptoms**:
- Workflows fail with 403 errors containing "rate limit" messages
- Keepalive instructions not posted due to API quota exhaustion
- Comment deduplication logic silently skips operations
- Orchestrator runs abort before completing all steps

**Root Cause**: The 20-minute scheduled orchestrator (`*/20 * * * *`) makes numerous paginated API calls without rate limit awareness or backoff strategies.

### Issue #2: Branch Sync Failures Abort Keepalive

**Severity**: High  
**Impact**: Keepalive iterations never complete their full cycle

**Symptoms**:
- Branch sync workflow exits on merge conflicts without retry
- Push failures terminate the entire keepalive chain
- No automatic recovery mechanism exists
- Human intervention required to unstick the process

**Root Cause**: `agents-keepalive-branch-sync.yml` uses a simple `git merge` approach with no conflict resolution strategy and no retry logic for transient push failures.

---

## 2. API Rate Limiting Analysis

### 2.1 Scheduled Workflow API Consumption

| Workflow | Schedule | API Calls Per Run (Estimated) | Daily Total |
|----------|----------|-------------------------------|-------------|
| `agents-70-orchestrator.yml` | `*/20 * * * *` (every 20 min) | 50-200+ | 3,600-14,400+ |
| `health-40-sweep.yml` | Weekly | 10-20 | ~3 |
| `health-41-repo-health.yml` | Weekly | 20-50 | ~7 |
| `maint-coverage-guard.yml` | Daily | 10-30 | 10-30 |
| `selftest-reusable-ci.yml` | Daily | 50-100 | 50-100 |

**Analysis**: The orchestrator alone can consume 3,600+ API calls daily, while GitHub's default rate limit is 5,000 requests/hour for authenticated users. During active periods with multiple PRs, this can easily exceed limits.

### 2.2 Orchestrator API Call Hotspots

Based on analysis of `agents-70-orchestrator.yml` (3,494 lines):

#### `idle-precheck` Job
```javascript
// Line ~160 - Paginated issue scan
await github.paginate(github.rest.issues.listForRepo, {...})
```
- **Calls**: 1 + (N/100) where N = open issues
- **Frequency**: Every run

#### `keepalive-guard` Job (via `keepalive_gate.js`)
```javascript
// Multiple paginate calls per PR evaluation:
- github.paginate(github.rest.issues.listComments)     // All comments
- github.paginate(github.rest.reactions.listForIssue)  // All reactions
- github.paginate(github.rest.actions.listWorkflowRuns) // Gate runs
- github.rest.pulls.get()                               // PR details
```
- **Calls per PR**: 5-15+ depending on comment volume
- **Total**: (5-15) × active_keepalive_PRs per run

#### `keepalive-instruction` Job
```javascript
// Line ~2630 - Reaction polling loop
while (Date.now() < deadline) {
  await github.paginate(github.rest.reactions.listForIssueComment)
  await github.rest.actions.listWorkflowRuns()
  await new Promise((resolve) => setTimeout(resolve, pollDelay));
}
```
- **Polling Duration**: Up to 180 seconds
- **Poll Interval**: 5 seconds
- **Calls per poll**: 2
- **Max calls**: 72 per keepalive instruction post

### 2.3 Helper Scripts with API Usage

| Script | Location | API Calls | Notes |
|--------|----------|-----------|-------|
| `keepalive_gate.js` | `.github/scripts/` | Heavy | `paginate` on comments, reactions, workflow runs |
| `comment-dedupe.js` | `.github/scripts/` | Moderate | Lists and manipulates comments |
| `issue_pr_locator.js` | `.github/scripts/` | Heavy | Multiple paginated searches |
| `detect-changes.js` | `.github/scripts/` | Light | Single PR files API call |

### 2.4 Rate Limit Handling (Current State)

**Good**: Some scripts have rate limit detection:
```javascript
// comment-dedupe.js, line 18
function isRateLimitError(error) {
  const message = String(error.message || '').toLowerCase();
  return message.includes('rate limit') || message.includes('ratelimit');
}
```

**Bad**: Detection exists but response is only to skip/warn, not retry:
```javascript
// comment-dedupe.js, line 106
if (isRateLimitError(error)) {
  warn(core, 'Rate limit while fetching existing comments; skipping docs-only comment management.');
  return;  // Silent failure
}
```

---

## 3. Keepalive Branch Sync Issues

### 3.1 Current Branch Sync Implementation

**File**: `.github/workflows/agents-keepalive-branch-sync.yml`

```yaml
- name: Sync branch (direct merge)
  run: |
    git fetch origin "$BASE_REF"
    
    if ! git merge origin/"$BASE_REF" --no-edit; then
      echo "::error::Merge conflict detected. Manual intervention required."
      git merge --abort || true
      exit 1  # FATAL - No recovery
    fi
    
    if ! git push origin HEAD:refs/heads/"$HEAD_REF"; then
      echo "::error::Failed to push synced branch."
      exit 1  # FATAL - No retry
    fi
```

### 3.2 Identified Failure Modes

| Failure Mode | Frequency | Current Handling | Impact |
|--------------|-----------|------------------|--------|
| **Merge Conflict** | Common | Exit with error | Keepalive stops entirely |
| **Push Rejection (race)** | Frequent | Exit with error | Sync incomplete |
| **Push Rejection (protection)** | Rare | Exit with error | Sync impossible |
| **Network Timeout** | Occasional | No handling | Exit with error |
| **Authentication Failure** | Rare | No handling | Exit with error |

### 3.3 Race Condition Analysis

The keepalive workflow has a fundamental race condition:

```
Timeline:
T0: Orchestrator reads PR head SHA = abc123
T1: Codex pushes new commit, head SHA = def456
T2: Orchestrator dispatches branch-sync with head_sha=abc123
T3: Branch-sync runs git merge on abc123
T4: Push fails because HEAD moved to def456
T5: Entire keepalive iteration aborts
```

This race is exacerbated by:
- No atomic operations in the sync workflow
- No pre-push verification of expected SHA
- No retry with re-fetch

### 3.4 Missing Recovery Mechanisms

1. **No Rebase Option**: Only merge is supported; rebases could resolve many conflicts automatically
2. **No Conflict Auto-Resolution**: Trivial conflicts (e.g., lock files) could be auto-resolved
3. **No Push Retry**: Transient failures cause permanent abort
4. **No Stale SHA Detection**: Workflow doesn't detect when input SHA is outdated
5. **No Status Reporting**: No label/comment added when sync fails, leaving PR in limbo

---

## 4. Workflow-Specific Bugs

### 4.1 `agents-70-orchestrator.yml`

| Bug ID | Description | Location | Severity |
|--------|-------------|----------|----------|
| O-1 | No rate limit backoff in paginate calls | Multiple jobs | High |
| O-2 | 180s polling loop can exhaust quotas | `keepalive-instruction` | High |
| O-3 | Token identity check makes extra API call | `token-preflight` | Low |
| O-4 | Comment scan doesn't use cursor pagination efficiently | `keepalive-prep` | Medium |
| O-5 | Workflow runs query lacks SHA filtering | `countActive()` | Medium |

### 4.2 `agents-keepalive-branch-sync.yml`

| Bug ID | Description | Location | Severity |
|--------|-------------|----------|----------|
| BS-1 | No retry on push failure | `Sync branch` step | High |
| BS-2 | Merge conflicts cause hard failure | `Sync branch` step | High |
| BS-3 | No fork-aware merge strategy | `Sync branch` step | Medium |
| BS-4 | Missing pre-sync SHA verification | Missing | High |
| BS-5 | No status label on failure | Missing | Medium |

### 4.3 `pr-00-gate.yml`

| Bug ID | Description | Location | Severity |
|--------|-------------|----------|----------|
| G-1 | Paginated artifact search can be slow | `summary` job | Low |
| G-2 | Comment deduplication races with other workflows | `summary` job | Medium |

### 4.4 `reusable-18-autofix.yml`

| Bug ID | Description | Location | Severity |
|--------|-------------|----------|----------|
| AF-1 | No rate limit handling on label operations | `autofix` job | Medium |
| AF-2 | Push without SHA verification can overwrite | `autofix` job | Medium |

---

## 5. Improvement Recommendations

### 5.1 API Rate Limit Mitigation

#### Immediate (High Priority)

**R-1: Implement Exponential Backoff Wrapper**

Create a reusable helper for all paginated API calls:

```javascript
// .github/scripts/api-helpers.js
async function paginateWithBackoff(github, method, params, options = {}) {
  const { maxRetries = 3, baseDelay = 1000 } = options;
  
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await github.paginate(method, params);
    } catch (error) {
      if (!isRateLimitError(error) || attempt === maxRetries) {
        throw error;
      }
      const delay = baseDelay * Math.pow(2, attempt);
      core.warning(`Rate limited; retrying in ${delay}ms (attempt ${attempt + 1}/${maxRetries})`);
      await sleep(delay);
    }
  }
}
```

**R-2: Add Rate Limit Pre-Check to Orchestrator**

```javascript
// At start of orchestrator
const { data: rateLimit } = await github.rest.rateLimit.get();
const remaining = rateLimit.resources.core.remaining;
const resetAt = rateLimit.resources.core.reset;

if (remaining < 500) {
  const resetTime = new Date(resetAt * 1000).toISOString();
  core.warning(`Rate limit low (${remaining} remaining). Resets at ${resetTime}. Deferring run.`);
  return;  // Skip this scheduled run
}
```

**R-3: Reduce Orchestrator Schedule Frequency**

Change from every 20 minutes to every 30 or 60 minutes during low-activity periods:

```yaml
on:
  schedule:
    # Every 30 minutes during business hours (UTC)
    - cron: '*/30 8-20 * * 1-5'
    # Every 60 minutes outside business hours
    - cron: '0 0-7,21-23 * * *'
    - cron: '0 * * * 0,6'
```

#### Medium-Term

**R-4: Implement Caching for Repeated Queries**

Cache PR metadata and comment lists within a single workflow run to avoid re-fetching:

```javascript
const prCache = new Map();
async function getPR(github, owner, repo, number) {
  const key = `${owner}/${repo}#${number}`;
  if (!prCache.has(key)) {
    const { data } = await github.rest.pulls.get({ owner, repo, pull_number: number });
    prCache.set(key, data);
  }
  return prCache.get(key);
}
```

**R-5: Use GraphQL for Bulk Queries**

Replace multiple REST calls with single GraphQL queries where possible:

```graphql
query KeepaliveContext($owner: String!, $repo: String!, $prNumber: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $prNumber) {
      headRefOid
      baseRefName
      headRefName
      labels(first: 20) { nodes { name } }
      comments(last: 50) {
        nodes {
          id
          body
          author { login }
          reactions(first: 10) { nodes { content } }
        }
      }
    }
  }
}
```

### 5.2 Branch Sync Improvements

#### Immediate (High Priority)

**R-6: Add Push Retry with Exponential Backoff**

```bash
push_with_retry() {
  local max_attempts=3
  local attempt=1
  local delay=2
  
  while [ $attempt -le $max_attempts ]; do
    if git push origin HEAD:refs/heads/"$HEAD_REF"; then
      return 0
    fi
    
    echo "Push failed (attempt $attempt/$max_attempts). Retrying in ${delay}s..."
    sleep $delay
    
    # Re-fetch and re-merge before retry
    git fetch origin "$BASE_REF" "$HEAD_REF"
    git reset --hard origin/"$HEAD_REF"
    git merge origin/"$BASE_REF" --no-edit || return 1
    
    attempt=$((attempt + 1))
    delay=$((delay * 2))
  done
  
  return 1
}
```

**R-7: Pre-Sync SHA Verification**

```bash
# Verify HEAD hasn't moved before attempting sync
current_sha=$(git rev-parse HEAD)
if [ "$current_sha" != "$EXPECTED_HEAD_SHA" ]; then
  echo "::warning::PR head has moved from $EXPECTED_HEAD_SHA to $current_sha. Aborting sync to avoid conflicts."
  exit 0  # Graceful exit, not failure
fi
```

**R-8: Add Failure Status Label**

When sync fails, apply a label so humans know intervention is needed:

```bash
# On failure, apply label
gh pr edit "$PR_NUMBER" --add-label "agents:sync-failed"
gh pr comment "$PR_NUMBER" --body "⚠️ Branch sync failed. Manual intervention required to resolve conflicts."
```

#### Medium-Term

**R-9: Implement Rebase-First Strategy**

Try rebase first, fall back to merge:

```bash
# Try rebase first (cleaner history)
if git rebase origin/"$BASE_REF"; then
  git push --force-with-lease origin HEAD:refs/heads/"$HEAD_REF"
  exit 0
fi

# Fall back to merge
git rebase --abort
git merge origin/"$BASE_REF" --no-edit
git push origin HEAD:refs/heads/"$HEAD_REF"
```

**R-10: Auto-Resolve Trivial Conflicts**

```bash
# Check if conflicts are only in lock files
conflict_files=$(git diff --name-only --diff-filter=U)
if echo "$conflict_files" | grep -qvE '(requirements.*\.lock|package-lock\.json|yarn\.lock|poetry\.lock)'; then
  echo "Non-trivial conflicts detected"
  exit 1
fi

# Auto-resolve lock files by accepting theirs
for file in $conflict_files; do
  git checkout --theirs "$file"
  git add "$file"
done
git commit --no-edit
```

### 5.3 Keepalive Flow Improvements

**R-11: Add Idempotency Keys**

Track sync attempts to avoid duplicate work:

```yaml
inputs:
  idempotency_key:
    description: Unique key for this sync attempt
    required: false

# In sync job
- name: Check idempotency
  run: |
    key="${{ inputs.idempotency_key }}"
    if [ -n "$key" ]; then
      # Check if this sync was already attempted
      marker=".sync-attempts/$key"
      if gh api "/repos/${{ github.repository }}/contents/$marker" &>/dev/null; then
        echo "Sync $key already attempted. Skipping."
        exit 0
      fi
    fi
```

**R-12: Implement Sync Status Tracking**

Create a persistent record of sync attempts:

```javascript
// After sync attempt (success or failure)
const status = {
  pr: prNumber,
  trace: inputs.trace,
  attempt: new Date().toISOString(),
  result: success ? 'success' : 'failure',
  reason: failureReason || null,
  head_before: inputs.head_sha,
  head_after: newHeadSha,
};

// Store in PR comment or workflow artifact for debugging
```

---

## 6. Implementation Priority

### Phase 1: Critical Fixes (1-2 weeks)

| ID | Task | Effort | Impact |
|----|------|--------|--------|
| R-2 | Rate limit pre-check in orchestrator | 2h | High |
| R-6 | Push retry with backoff in branch-sync | 4h | High |
| R-7 | Pre-sync SHA verification | 2h | High |
| R-8 | Failure status label application | 2h | Medium |

### Phase 2: Rate Limit Mitigation (2-4 weeks)

| ID | Task | Effort | Impact |
|----|------|--------|--------|
| R-1 | Exponential backoff wrapper | 4h | High |
| R-3 | Reduce orchestrator schedule frequency | 1h | Medium |
| R-4 | In-run caching for repeated queries | 8h | Medium |

### Phase 3: Robustness (4-6 weeks)

| ID | Task | Effort | Impact |
|----|------|--------|--------|
| R-5 | GraphQL bulk queries | 16h | Medium |
| R-9 | Rebase-first strategy | 4h | Medium |
| R-10 | Auto-resolve trivial conflicts | 8h | Medium |
| R-11 | Idempotency keys | 4h | Low |
| R-12 | Sync status tracking | 8h | Low |

---

## Appendix A: Workflow Schedule Summary

| Workflow | Schedule | Purpose |
|----------|----------|---------|
| `agents-70-orchestrator.yml` | `*/20 * * * *` | Keepalive sweep |
| `health-40-sweep.yml` | `5 5 * * 1` | Workflow lint |
| `health-40-repo-selfcheck.yml` | `20 6 * * 1` | Repository validation |
| `health-41-repo-health.yml` | `15 7 * * 1` | Stale content tracking |
| `health-50-security-scan.yml` | `30 1 * * 0` | Security scanning |
| `maint-coverage-guard.yml` | `45 6 * * *` | Coverage enforcement |
| `maint-50-tool-version-check.yml` | `0 8 * * 1` | Tool version audit |
| `maint-51-dependency-refresh.yml` | `0 4 1,15 * *` | Dependency updates |
| `selftest-reusable-ci.yml` | `30 6 * * *` | CI self-validation |
| `security.yml` | `30 1 * * 0` | Legacy security scan |

---

## Appendix B: API Call Audit Checklist

Use this checklist when adding new workflow logic:

- [ ] Does the new code use `github.paginate`? If so, wrap with rate limit handling.
- [ ] Is there a polling loop? Ensure reasonable timeout and backoff.
- [ ] Are multiple API calls made for the same resource? Consider caching.
- [ ] Could this query be combined with others using GraphQL?
- [ ] Is the workflow scheduled? Ensure schedule doesn't overlap with others.
- [ ] On failure, does the workflow leave the system in a recoverable state?

---

## Appendix C: Related Files

| File | Purpose |
|------|---------|
| `.github/workflows/agents-70-orchestrator.yml` | Main keepalive orchestrator |
| `.github/workflows/agents-keepalive-branch-sync.yml` | Branch sync workflow |
| `.github/scripts/keepalive_gate.js` | Gate evaluation logic |
| `.github/scripts/comment-dedupe.js` | Comment management with rate limit detection |
| `.github/scripts/api-helpers.js` | (Proposed) Shared API utilities |
