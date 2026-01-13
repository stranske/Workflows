# GitHub API Rate Limit Management

> **Last Updated:** 2026-01-13  
> **Status:** Active architecture document

This document describes the rate limit management strategy for repositories using the stranske/Workflows automation templates.

## Executive Summary

The workflow system uses a **multi-token architecture** to maximize effective API capacity from 5,000 requests/hour (single token) to **25,000+ requests/hour** across multiple independent rate limit pools.

| Token Type | Pool Size | Count | Total Capacity |
|------------|-----------|-------|----------------|
| GitHub Apps | 5,000/hr each | 3 | 15,000/hr |
| PATs (owner) | 5,000/hr | 1 | 5,000/hr |
| PATs (service bot) | 5,000/hr | 1 | 5,000/hr |
| **Combined** | | | **25,000/hr** |

## Conclusions from Rate Limit Analysis

### Root Cause of Failures

Recent workflow failures (run 20941728300 and others) were caused by:

1. **Installation token exhaustion**: The shared `GITHUB_TOKEN` hit its 5,000/hr limit
2. **No effective fallback**: Retry logic used the same exhausted token
3. **Cascade amplification**: ~100 workflow runs in 1 hour, each making 5-15 API calls

### Key Findings

- **Workflow volume**: 14-15 runs/hour for high-frequency workflows (PR Meta, Keepalive, Bot Handler)
- **API calls per run**: 8-15 calls depending on workflow complexity
- **Peak usage**: 600-800 calls/hour during active development
- **Cascade trigger**: Single push can spawn 15-20+ workflow runs

### What Worked

- Three-app architecture provides isolated pools ✅
- Fallback chain logic exists in keepalive workflow ✅
- Retry with exponential backoff handles transient errors ✅

### What Failed

- Summary job used `GITHUB_TOKEN` instead of minted app token ❌
- Token switching only happens at job start, not mid-execution ❌
- No proactive switching before exhaustion ❌

## Recommended Architecture

### Token Assignment

```
┌─────────────────────────────────────────────────────────────────┐
│                    KEEPALIVE_APP Pool (5000/hr)                 │
│  agents-keepalive-loop (isolated, high-frequency)               │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    WORKFLOWS_APP Pool (5000/hr)                 │
│  agents-autofix-loop, autofix                                   │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                       GH_APP Pool (5000/hr)                     │
│  agents-issue-intake, agents-bot-comment-handler                │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                   SERVICE_BOT_PAT Pool (5000/hr)                │
│  PRIMARY: Bot-attributed comments (unique identity requirement) │
│  SECONDARY: Fallback when app tokens fail to mint               │
│  ⚠️ Reserve capacity - don't use as universal fallback          │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    OWNER_PR_PAT Pool (5000/hr)                  │
│  PRIMARY: PR creation with human attribution                    │
│  SECONDARY: Universal fallback for rate limit exhaustion        │
│  ✅ Better fallback choice - higher capacity, less critical role│
└─────────────────────────────────────────────────────────────────┘
```

### Fallback Chain (Per Workflow)

Every workflow should implement:

```
Primary App Token → OWNER_PR_PAT (fallback) → GITHUB_TOKEN (last resort)
```

**Important:** SERVICE_BOT_PAT should NOT be the universal fallback. It has a unique role (posting comments as the automation account) that requires its pool to remain available.

Example implementation:

```yaml
- name: Select API token
  id: token
  env:
    APP_TOKEN: ${{ steps.app_token.outputs.token }}
    OWNER_PAT: ${{ secrets.OWNER_PR_PAT }}
    GITHUB_TOKEN_FALLBACK: ${{ secrets.GITHUB_TOKEN }}
  run: |
    if [ -n "$APP_TOKEN" ]; then
      echo "token=$APP_TOKEN" >> "$GITHUB_OUTPUT"
      echo "source=app" >> "$GITHUB_OUTPUT"
    elif [ -n "$OWNER_PAT" ]; then
      echo "::warning::App token unavailable, using OWNER_PR_PAT fallback"
      echo "token=$OWNER_PAT" >> "$GITHUB_OUTPUT"
      echo "source=owner-pat" >> "$GITHUB_OUTPUT"
    else
      echo "token=$GITHUB_TOKEN_FALLBACK" >> "$GITHUB_OUTPUT"
      echo "source=github-token" >> "$GITHUB_OUTPUT"
    fi
```

### Proactive Rate Limit Switching

Don't wait for exhaustion - switch when approaching limits:

```javascript
async function apiCallWithProactiveSwitch(github, fallbackGithub, apiCall) {
  const response = await apiCall(github);
  
  // Check remaining quota from response headers
  const remaining = parseInt(response.headers['x-ratelimit-remaining'], 10);
  
  if (remaining < 100) {
    core.warning(`Rate limit low (${remaining} remaining), switching to fallback for subsequent calls`);
    return { response, switchToFallback: true };
  }
  
  return { response, switchToFallback: false };
}
```

This allows mid-execution switching rather than waiting for failure.

### Required Secrets

| Secret | Required | Purpose |
|--------|----------|---------|
| `KEEPALIVE_APP_ID` | Yes | Keepalive-loop dedicated app |
| `KEEPALIVE_APP_PRIVATE_KEY` | Yes | Keepalive-loop dedicated app |
| `WORKFLOWS_APP_ID` | Yes | Autofix workflows |
| `WORKFLOWS_APP_PRIVATE_KEY` | Yes | Autofix workflows |
| `GH_APP_ID` | Recommended | Issue/comment handling |
| `GH_APP_PRIVATE_KEY` | Recommended | Issue/comment handling |
| `SERVICE_BOT_PAT` | **Critical** | Bot-identity comments (reserve capacity!) |
| `OWNER_PR_PAT` | **Critical** | Human attribution + universal fallback |

## Optimization Recommendations

> **Note:** These are documented recommendations. Implementation requires changes to workflow files and scripts - not yet done.

### 1. Pass Data Between Jobs (Don't Re-fetch)

**Before:** Each job fetches PR data independently (3+ calls)
```yaml
jobs:
  job-a:
    steps:
      - run: gh pr view $PR --json body  # API call
  job-b:
    steps:
      - run: gh pr view $PR --json body  # Duplicate call
```

**After:** Fetch once, pass via outputs
```yaml
jobs:
  fetch:
    outputs:
      pr_body: ${{ steps.fetch.outputs.body }}
    steps:
      - id: fetch
        run: echo "body=$(gh pr view $PR --json body -q .body)" >> "$GITHUB_OUTPUT"
  job-a:
    needs: fetch
    # Use: ${{ needs.fetch.outputs.pr_body }}
```

### 2. Batch Label Operations

**Before:** Multiple calls
```javascript
await github.rest.issues.addLabels({ labels: ['a'] });
await github.rest.issues.addLabels({ labels: ['b'] });
```

**After:** Single call
```javascript
await github.rest.issues.addLabels({ labels: ['a', 'b'] });
```

### 3. Add Path Filters

Skip workflows for irrelevant changes:

```yaml
on:
  pull_request:
    paths:
      - 'src/**'
      - 'tests/**'
      - '!docs/**'  # Skip for docs-only
```

### 4. Tighten Concurrency

Prevent duplicate runs:

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.event.pull_request.number }}
  cancel-in-progress: true
```

### 5. Proactive Rate Limit Switching (Medium Effort)

Check `x-ratelimit-remaining` header and switch tokens before exhaustion:

```javascript
async function withRateLimitAwareness(primaryClient, fallbackClient, apiCall) {
  let client = primaryClient;
  
  const response = await apiCall(client);
  const remaining = parseInt(response.headers['x-ratelimit-remaining'], 10);
  
  if (remaining < 100 && fallbackClient) {
    console.log(`Switching to fallback (${remaining} remaining)`);
    client = fallbackClient;
  }
  
  return { response, client };
}
```

**Effort:** 2-3 days | **Files:** `github-api-with-retry.js`, all scripts using it

### 6. GraphQL Batching (Medium Effort)

Replace multiple REST calls with single GraphQL query:

```graphql
# Before: 4 REST calls
# GET /pulls/{number}, /pulls/{number}/files, /issues/{number}/labels, /issues/{number}/comments

# After: 1 GraphQL call
query PRContext($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      body
      title
      files(first: 100) { nodes { path } }
      labels(first: 20) { nodes { name } }
      comments(last: 10) { nodes { body author { login } } }
    }
  }
}
```

**Effort:** 2-3 days | **Reduction:** 60-80% for multi-fetch operations

## Optimization Effort Summary

| Optimization | API Reduction | Effort | Status |
|-------------|---------------|--------|--------|
| **Low Effort (Hours)** |
| Batch label operations | 50-70% for labels | 1-2 hrs | 📋 Backlog |
| Path filters on workflows | 20-40% runs | 1-2 hrs | 📋 Backlog |
| Tighter concurrency groups | 10-30% runs | 1 hr | 📋 Backlog |
| **Medium Effort (Days)** |
| Pass PR data via outputs | 30-50% | 1-2 days | 📋 Backlog |
| Proactive rate limit switching | Prevents failures | 2-3 days | 📋 Backlog |
| GraphQL batching | 60-80% | 2-3 days | 📋 Backlog |
| **High Effort (Weeks)** |
| Central API caching layer | 50-70% | 1-2 weeks | 📋 [Issue #868](https://github.com/stranske/Workflows/issues/868) |
| Workflow consolidation | 30-50% runs | 1-2 weeks | 📋 [Issue #869](https://github.com/stranske/Workflows/issues/869) |
| Event debouncing | 40-60% runs | 1 week | 📋 [Issue #870](https://github.com/stranske/Workflows/issues/870) |

## Monitoring & Troubleshooting

### Check Rate Limits

```bash
# Current status
gh api rate_limit --jq '.resources.core'

# All resources
gh api rate_limit --jq '.resources | to_entries[] | "\(.key): \(.value.remaining)/\(.value.limit)"'
```

### Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| "API rate limit exceeded for installation" | App token exhausted | Wait for reset or use PAT fallback |
| "API rate limit exceeded" | PAT exhausted | Use different PAT or wait |
| 429 status | Secondary rate limit | Exponential backoff (already implemented) |

### Emergency Pause

Remove `agents:keepalive` label to halt keepalive operations.

## Creating GitHub Apps

1. Go to https://github.com/settings/apps/new
2. Name: `<repo>-keepalive-app` (or similar)
3. Permissions:
   - Repository: `contents: write`, `pull-requests: write`, `actions: write`
   - Optional: `issues: write`
4. Generate private key → downloads `.pem` file
5. Install on repository
6. Add secrets:
   - `*_APP_ID`: Numeric app ID from settings page
   - `*_APP_PRIVATE_KEY`: Full contents of `.pem` file

## Summary

**Problem:** Single token pool (5,000/hr) insufficient for high-frequency automation.

**Solution:** Multi-token architecture with:
- 3 GitHub Apps (15,000/hr)
- 2 PATs from different accounts (10,000/hr)
- Automatic fallback chain with proactive switching

**Key Action Items:**
1. ✅ KEEPALIVE_APP already implemented on main
2. ✅ SERVICE_BOT_PAT reserved for bot-identity comments (not universal fallback)
3. ⚠️ Use OWNER_PR_PAT as universal fallback instead
4. ⚠️ Verify all workflow jobs use minted app tokens, not raw GITHUB_TOKEN
5. 📋 Implement proactive rate limit switching (check `x-ratelimit-remaining`)
6. 📋 Consider API call reduction optimizations for sustained high volume

---

## Related Documentation

- [INTEGRATION_GUIDE.md](../INTEGRATION_GUIDE.md) - Consumer repo setup
- [SYNC_WORKFLOW.md](../SYNC_WORKFLOW.md) - Template sync process
- [keepalive/](../keepalive/) - Keepalive workflow details
