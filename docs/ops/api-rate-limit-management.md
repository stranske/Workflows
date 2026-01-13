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
│  Universal fallback for ALL workflows                           │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    OWNER_PR_PAT Pool (5000/hr)                  │
│  PR creation with human attribution                             │
└─────────────────────────────────────────────────────────────────┘
```

### Fallback Chain (Per Workflow)

Every workflow should implement:

```
Primary App Token → SERVICE_BOT_PAT → GITHUB_TOKEN (last resort)
```

Example implementation:

```yaml
- name: Select API token
  id: token
  env:
    APP_TOKEN: ${{ steps.app_token.outputs.token }}
    SERVICE_BOT_PAT: ${{ secrets.SERVICE_BOT_PAT }}
    GITHUB_TOKEN_FALLBACK: ${{ secrets.GITHUB_TOKEN }}
  run: |
    if [ -n "$APP_TOKEN" ]; then
      echo "token=$APP_TOKEN" >> "$GITHUB_OUTPUT"
      echo "source=app" >> "$GITHUB_OUTPUT"
    elif [ -n "$SERVICE_BOT_PAT" ]; then
      echo "::warning::App token unavailable, using SERVICE_BOT_PAT"
      echo "token=$SERVICE_BOT_PAT" >> "$GITHUB_OUTPUT"
      echo "source=pat" >> "$GITHUB_OUTPUT"
    else
      echo "token=$GITHUB_TOKEN_FALLBACK" >> "$GITHUB_OUTPUT"
      echo "source=github-token" >> "$GITHUB_OUTPUT"
    fi
```

### Required Secrets

| Secret | Required | Purpose |
|--------|----------|---------|
| `KEEPALIVE_APP_ID` | Yes | Keepalive-loop dedicated app |
| `KEEPALIVE_APP_PRIVATE_KEY` | Yes | Keepalive-loop dedicated app |
| `WORKFLOWS_APP_ID` | Yes | Autofix workflows |
| `WORKFLOWS_APP_PRIVATE_KEY` | Yes | Autofix workflows |
| `GH_APP_ID` | Recommended | Issue/comment handling |
| `GH_APP_PRIVATE_KEY` | Recommended | Issue/comment handling |
| `SERVICE_BOT_PAT` | **Critical** | Universal fallback (separate account) |
| `OWNER_PR_PAT` | Optional | Human-attributed PR creation |

## Optimization Recommendations

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
- Automatic fallback chain

**Key Action Items:**
1. ✅ KEEPALIVE_APP already implemented on main
2. ⚠️ Ensure SERVICE_BOT_PAT is from a **different account** than OWNER_PR_PAT
3. ⚠️ Verify all workflow jobs use minted app tokens, not raw GITHUB_TOKEN
4. 📋 Consider API call reduction optimizations for sustained high volume

---

## Related Documentation

- [INTEGRATION_GUIDE.md](../INTEGRATION_GUIDE.md) - Consumer repo setup
- [SYNC_WORKFLOW.md](../SYNC_WORKFLOW.md) - Template sync process
- [keepalive/](../keepalive/) - Keepalive workflow details
