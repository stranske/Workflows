# Auto-Pilot Fix History & Current Issues

**Created:** 2026-01-13
**Status:** INVESTIGATION COMPLETE - ROOT CAUSES IDENTIFIED

## Executive Summary

The `agents:auto-pilot` workflow has been the subject of **32 PRs** since its initial implementation on 2026-01-10. Despite numerous fixes, two issues remain unresolved:

1. **Issue #862 (Workflows repo):** Failing due to **excessively large issue body** (135,021 characters) causing OpenAI rate limit errors (token limit exceeded)
2. **Issue #1127 (Portable-Alpha-Extension-Model repo):** Failing due to **missing required script file** (`github-api-with-retry.js`) in consumer repo

---

## Root Cause Analysis

### Issue #862 (stranske/Workflows)

**Error from workflow run ID 20939133934:**
```
openai.RateLimitError: Error code: 429 - {'error': {'message': 'Request too large for gpt-4o in 
organization org-exXNr4VgADNdan0SgAn5hevN on tokens per min (TPM): Limit 30000, Requested 33926. 
The input or output tokens must be reduced in order to run successfully.'}}
```

**Root Cause:** The issue body has been corrupted by recursive task decomposition spam, inflating it to **135,021 characters** (~33,926 tokens). The LLM formatter cannot process this because it exceeds OpenAI's TPM limit of 30,000.

**Evidence:**
- Issue body size: `gh api repos/stranske/Workflows/issues/862 --jq '.body' | wc -c` → **135,021**
- Normal issue size (e.g., #1127): **1,714 characters**

**Fix Required:**
1. Truncate or reset the issue body to its original content
2. Add size limits to the formatter to prevent processing excessively large issues ✅ **IMPLEMENTED**
3. Add fallback handling for rate limit errors

**FIX STATUS:** Partial fix implemented in `scripts/langchain/issue_formatter.py`:
- Added `MAX_ISSUE_BODY_SIZE = 50000` check in `format_issue_body()`
- Returns clear error message when issue exceeds limit
- Still need to clean up issue #862's body manually

**Resolution Steps for Issue #862:**
1. View the bloated issue: `gh issue view 862 --repo stranske/Workflows`
2. Edit to remove recursive task decomposition spam
3. Or re-create the issue with clean content
4. Re-trigger auto-pilot

---

### Issue #1127 (stranske/Portable-Alpha-Extension-Model)

**Error from workflow run ID 20934021234:**
```
Error: Cannot find module '/home/runner/work/Portable-Alpha-Extension-Model/Portable-Alpha-Extension-Model/.github/scripts/github-api-with-retry.js'
```

**Root Cause:** The consumer repo `Portable-Alpha-Extension-Model` is missing the required script file `.github/scripts/github-api-with-retry.js` that the auto-pilot workflow depends on.

**Evidence:**
- Workflow fails immediately at the "Determine context" step
- The script is required by the workflow but not synced to consumer repos

**FIX STATUS: READY TO MERGE** ✅

The script IS in `sync-manifest.yml` at line 246. A sync PR **#1131** exists in the consumer repo with all checks passing:
- Created: 2026-01-12T22:40:32Z
- Contains: `.github/scripts/github-api-with-retry.js`
- Status: All 14 checks passed, 9 skipped

**Resolution:**
1. Merge PR https://github.com/stranske/Portable-Alpha-Extension-Model/pull/1131
2. Re-trigger auto-pilot on issue #1127

---

## Complete PR History (32 PRs)

### Phase 1: Initial Implementation (2026-01-10)

| PR | Title | Status | Description |
|----|-------|--------|-------------|
| #740 | feat: Implement auto-pilot workflow (Phase 4C) | MERGED | Initial implementation of end-to-end automation |
| #743 | feat(auto-pilot): Auto-create PR when agent branch exists | MERGED | Added PR creation when branch exists |
| #745 | [Auto-pilot] [Test] Auto-pilot PR creation test | CLOSED | Test PR |
| #747 | [Auto-pilot] [Test] Full auto-pilot e2e validation | CLOSED | Test PR |
| #748 | feat(sync): Add agents-auto-pilot.yml to consumer repo sync | MERGED | Added workflow to sync manifest |
| #750 | [Auto-pilot] Add timestamp logging to keepalive_state.js | CLOSED | Logging enhancement |
| #751 | fix(auto-pilot): Add agent labels to PR after creation | MERGED | Added agent labels to created PRs |
| #753 | [Auto-pilot] Add debug log to prompt_injection_guard.js | CLOSED | Debug logging |
| #754 | Auto pilot pr labels | MERGED | PR label fixes |
| #756 | [Auto-pilot] Add entry log to error_classifier.js | MERGED | Error classification logging |
| #757 | fix(auto-pilot): Add verify label to PR, add Closes keyword | MERGED | Verification and closing fixes |

### Phase 2: Re-dispatch & Pipeline Flow (2026-01-10)

| PR | Title | Status | Description |
|----|-------|--------|-------------|
| #760 | [Auto-pilot] Add entry/exit logging to resetState() | CLOSED | State reset logging |
| #762 | Auto pilot pr labels | CLOSED | Label fixes |
| #764 | [Auto-pilot] Add entry/exit logging to resetState() | MERGED | State reset logging |
| #765 | feat(auto-pilot): Add automatic re-triggering on prep labels | MERGED | Re-trigger mechanism |
| #767 | feat(auto-pilot): Add self re-dispatch for pipeline continuation | MERGED | Self re-dispatch for continuation |
| #769 | [Auto-pilot] Add debug mode flag to formatTimestamp() | MERGED | Debug timestamps |
| #770 | fix(auto-pilot): Dispatch keepalive after PR creation | MERGED | Keepalive dispatch fix |
| #772 | [Auto-pilot] Add elapsed time tracking to keepalive state | MERGED | Time tracking |

### Phase 3: Step Ordering & Completion (2026-01-11)

| PR | Title | Status | Description |
|----|-------|--------|-------------|
| #776 | fix: Auto-pilot step ordering - optimize/apply before agent | MERGED | Fixed step order |
| #778 | [Auto-pilot] Add hello world test function | CLOSED | Test function |
| #780 | fix: Add autopilot completion check and fix keepalive loop | MERGED | Completion checking |
| #783 | fix: Autopilot completion check and auto-label interference | MERGED | Fixed label interference |
| #787 | [Auto-pilot] Add workflow execution timeout configuration | MERGED | Timeout configuration |
| #794 | Fix/autopilot step order | MERGED | Step order fixes |

### Phase 4: Race Conditions & Intake Interference (2026-01-12)

| PR | Title | Status | Description |
|----|-------|--------|-------------|
| #813 | [Auto-pilot] [Metrics] Create Metrics Collection Workflow | CLOSED | Metrics collection |
| #819 | fix: Auto-pilot race condition + sync all missing scripts | MERGED | Race condition fix, script sync |
| #832 | chore(auto-pilot): bootstrap PR for issue #821 | MERGED | Bootstrap PR |
| #834 | fix: Skip intake workflow when agents:auto-pilot is managing | MERGED | Skip intake when auto-pilot active |
| #835 | fix: Apply auto-pilot exclusion to consumer repo thin caller | MERGED | Consumer repo exclusion |
| #837 | fix: Use exact array match for agents:auto-pilot label check | MERGED | Exact label matching |
| #852 | fix(agents): Enable auto-pilot PR creation by forcing mode | MERGED | PR creation mode override |

---

## Key Problems Identified Over 32 PRs

1. **Race conditions** between auto-pilot and other workflows (intake, auto-label)
2. **Step ordering issues** - optimizer/apply needed before agent assignment  
3. **Re-dispatch failures** - pipeline not continuing after steps
4. **Label interference** - other workflows triggering when auto-pilot active
5. **Missing scripts in consumer repos** - required JS files not synced
6. **No size limits on issue processing** - allows oversized issues to crash LLM calls

---

## Required Fixes

### Fix 1: Handle Large Issue Bodies (for Issue #862)

**File:** `scripts/langchain/issue_formatter.py`

Add size check and truncation:
```python
MAX_ISSUE_BODY_SIZE = 50000  # ~12,500 tokens, safe margin under 30k limit

def format_issue_body(issue_body: str, use_llm: bool = True) -> dict:
    if len(issue_body) > MAX_ISSUE_BODY_SIZE:
        # Either truncate or return error
        return {
            "error": f"Issue body too large ({len(issue_body)} chars). Max is {MAX_ISSUE_BODY_SIZE}.",
            "formatted_body": None
        }
    # ... rest of function
```

### Fix 2: Merge Sync PR (for Issue #1127)

**Action Required:** Merge PR #1131 in Portable-Alpha-Extension-Model

```bash
# View the PR
gh pr view 1131 --repo stranske/Portable-Alpha-Extension-Model

# Merge (requires write access)
gh pr merge 1131 --repo stranske/Portable-Alpha-Extension-Model --squash
```

The sync manifest already contains `github-api-with-retry.js` at line 246.

### Fix 3: Add Rate Limit Retry Logic

**File:** `scripts/langchain/issue_formatter.py`

Add retry with exponential backoff for rate limit errors.

### Fix 4: Clean Up Issue #862

The issue body needs to be manually reset to its original content (remove recursive decomposition spam).

---

## Verification Commands

Check issue #862 body size:
```bash
gh api repos/stranske/Workflows/issues/862 --jq '.body' | wc -c
```

Check if script exists in consumer repo:
```bash
gh api repos/stranske/Portable-Alpha-Extension-Model/contents/.github/scripts/github-api-with-retry.js
```

Check recent auto-pilot runs:
```bash
gh api repos/stranske/Workflows/actions/workflows/agents-auto-pilot.yml/runs --jq '.workflow_runs[:10] | .[] | {id, conclusion, created_at}'
```
