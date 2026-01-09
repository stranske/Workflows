# Workflow Audit Results - January 9, 2026

## Executive Summary

**Status:** 🔴 **Multiple Critical Issues Found and Fixed**

The agent workflows were non-functional in the Workflows repo due to:
1. Missing PYTHONPATH configuration
2. Missing Phase 3 workflow files
3. Missing labels

All issues have been fixed in PR #694.

---

## Issues Found

### 🔴 Critical: PYTHONPATH Missing (ModuleNotFoundError)

**Affected Workflow:** `agents-issue-optimizer.yml`

**Symptom:** Workflow runs but fails with:
```
ModuleNotFoundError: No module named 'tools'
```

**Root Cause:** Python scripts import from `tools.llm_provider` but PYTHONPATH env var was not set in workflow steps.

**Evidence:**
- Issue #691: agents:optimize label added → workflow triggered → failed
- Workflow run 20853983471: Failed with ModuleNotFoundError
- Template version has `PYTHONPATH: ${{ github.workspace }}` but Workflows repo version didn't

**Impact:** 
- `agents:optimize` label → workflow fails
- `agents:apply-suggestions` label → workflow fails  
- `agents:format` label → workflow fails
- All Phase 2 functionality broken in Workflows repo

**Fix Applied:** Added `PYTHONPATH: ${{ github.workspace }}` to 4 workflow steps in agents-issue-optimizer.yml

**Status:** ✅ Fixed in PR #694

---

### 🔴 Critical: Phase 3 Workflows Missing

**Affected Workflows:** 
- `agents-capability-check.yml` 
- `agents-decompose.yml`
- `agents-dedup.yml`

**Symptom:** Labels exist but workflows don't trigger.

**Root Cause:** These workflows only exist in `templates/consumer-repo/.github/workflows/` and were never copied to the Workflows repo's `.github/workflows/`.

**Evidence:**
```bash
$ ls .github/workflows/agents-capability-check.yml
ls: cannot access '.github/workflows/agents-capability-check.yml': No such file or directory
```

**Impact:**
- `agents:decompose` label → no effect
- `agent:codex` label → capability check never runs
- New issues → duplicate detection never runs
- Phase 3 completely non-functional in Workflows repo

**Fix Applied:** 
1. Copied 3 workflow files from template
2. Adapted for Workflows repo:
   - Removed self-checkout step (was checking out Workflows into subdirectory)
   - Changed `PYTHONPATH: ${{ github.workspace }}/workflows-repo` → `${{ github.workspace }}`
   - Removed `cd workflows-repo` commands
   - Changed Python 3.12 → 3.11 (repo standard)

**Status:** ✅ Fixed in PR #694

---

### 🔴 Critical: agents-auto-label.yml Path Issues

**Affected Workflow:** `agents-auto-label.yml`

**Symptom:** Would fail with similar path issues when triggered.

**Root Cause:** Same as above - workflow had self-checkout logic and wrong paths.

**Fix Applied:** Updated to use simple checkout and correct paths.

**Status:** ✅ Fixed in PR #694

---

### 🟡 Medium: Missing Labels

**Affected Labels:**
- `agents:optimize`
- `agents:formatted`
- `agents:decompose`
- `needs-human`
- `verify:checkbox`
- `verify:evaluate`
- `verify:compare`
- `verify:create-issue`

**Symptom:** Workflows look for labels that don't exist in the repo.

**Root Cause:** Sync workflow creates these labels in consumer repos but never created them for Workflows repo itself.

**Impact:** Labels couldn't be applied before fix (would need manual creation).

**Fix Applied:** Created all 8 missing labels via `gh label create`.

**Status:** ✅ Fixed (labels created, documented in SHORT_TERM_PLAN.md)

---

## Verification Testing

### Test 1: Issue #691 - agents:optimize

**Before Fix:**
- Label added: ✅ 
- Workflow triggered: ✅
- Workflow succeeded: ❌ Failed with ModuleNotFoundError
- Comment posted: ❌ No

**After Fix (Expected):**
- Label added: ✅
- Workflow triggered: ✅ 
- Workflow succeeded: ✅
- Comment posted: ✅

**How to Test:** Remove and re-add `agents:optimize` label on issue #691 after PR #694 merges.

---

### Test 2: Phase 3 Workflows

**Before Fix:**
- Workflows exist: ❌ No
- Labels work: ❌ No effect

**After Fix (Expected):**
- Workflows exist: ✅ Yes
- `agents:decompose` works: ✅
- `agent:codex` triggers capability check: ✅
- New issues trigger dedup: ✅

**How to Test:** 
1. Create test issue, add `agents:decompose` label
2. Create test issue, add `agent:codex` label
3. Create new issue similar to existing one (auto-triggers dedup)

---

## Root Cause Analysis

### Why This Happened

**Problem:** Template drift between consumer repos and Workflows repo itself.

**Contributing Factors:**
1. **Workflows treated differently:** Consumer repos get workflows via sync, but Workflows repo workflows are maintained separately
2. **No self-test:** Workflows repo doesn't run its own agent commands regularly
3. **Template-first development:** New workflows added to template but not backported to Workflows repo
4. **PYTHONPATH oversight:** Template had fix but Workflows repo version diverged

### Lessons Learned

1. **Test on source repo:** When developing workflows that will be synced, also test them in the Workflows repo itself
2. **Keep in sync:** Workflows in Workflows repo should match template versions (with path adaptations)
3. **Add CI check:** Could add workflow that validates Workflows repo has all workflows that consumer repos get

---

## Recommendations

### Immediate (This PR)

✅ All issues fixed in PR #694

### Short Term (Next 2 Weeks)

1. **Test all workflows in Workflows repo:**
   - Create test issues for each Phase 3 workflow
   - Verify they work as expected
   - Document results in SHORT_TERM_PLAN.md

2. **Sync check script:**
   - Create script to compare `.github/workflows/` with `templates/consumer-repo/.github/workflows/`
   - Flag missing or divergent workflows
   - Run in CI

### Medium Term (Phase 4)

3. **Self-test workflow:**
   - Periodic workflow that tests agent commands in Workflows repo
   - Creates test issue, applies labels, verifies results
   - Alerts if workflows broken

4. **Template versioning:**
   - Track which template version each consumer repo is on
   - Track which version Workflows repo itself uses
   - Alert on version skew

---

## Summary Table

| Issue | Severity | Workflows Affected | Status | PR |
|-------|----------|-------------------|--------|-----|
| Missing PYTHONPATH | 🔴 Critical | agents-issue-optimizer.yml | ✅ Fixed | #694 |
| Missing Phase 3 workflows | 🔴 Critical | capability-check, decompose, dedup | ✅ Fixed | #694 |
| Wrong paths in auto-label | 🔴 Critical | agents-auto-label.yml | ✅ Fixed | #694 |
| Missing labels | 🟡 Medium | All agent workflows | ✅ Fixed | Manual |

**Total Issues:** 4  
**Issues Fixed:** 4  
**Issues Remaining:** 0

---

## Next Steps

1. ✅ PR #694 created with all fixes
2. ⏳ Merge PR #694
3. ⏳ Test issue #691 (remove/re-add agents:optimize label)
4. ⏳ Execute Phase 3 functional tests per SHORT_TERM_PLAN.md
5. ⏳ Create sync check script

---

## Related Documents

- PR #694: https://github.com/stranske/Workflows/pull/694
- SHORT_TERM_PLAN.md: docs/plans/SHORT_TERM_PLAN.md
- Original issue: #691
- Rollout plan: docs/plans/langchain-post-code-rollout.md
