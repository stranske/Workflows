<!-- bootstrap for gemini on issue #4514 run:42380991219-1 -->

# Issue #4514 - Cross-Repository Evidence Validation

## Overview
This document records the implementation and validation of downstream run evidence resolution for issue #4514, focusing on the exact #4509 capture and cross-repository provenance handling.

## Authentication Evidence

### GitHub API Response: stranske/trip-planner Run 42327976097

**Command:** `gh api repos/stranske/trip-planner/actions/runs/42327976097`

**Authenticated Response:**
- Run ID: 42327976097
- Status: completed
- Conclusion: success
- Repository: stranske/trip-planner
- Head SHA: 948406465cf7cd65d1ac92206b4514aaad455443
- Event: pull_request
- Run Attempt: 1
- Head Branch: sync/workflows-candidate
- Referenced Workflows: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main (sha: 37e230009cdba04743376410c9f72356b85fb64f)

**Verification:**
- ✅ Run ID: 42327976097
- ✅ Repository: stranske/trip-planner
- ✅ Status: completed
- ✅ Conclusion: success
- ✅ Head SHA: 948406465cf7cd65d1ac92206b4514aaad455443

### GitHub API Response: stranske/Workflows Run 42327976097 (404)

**Command:** `gh api --include repos/stranske/Workflows/actions/runs/42327976097`

**Authenticated Response:**
```
HTTP/2.0 404 Not Found
```

**Verification:**
- ✅ HTTP 404 returned as expected
- ✅ Does NOT override the authenticated consumer result from trip-planner
- ✅ Proves run 42327976097 exists in stranske/trip-planner, not in stranske/Workflows

## Exact #4509 Capture

### Issue #4509 Details
- **Commit:** 37e230009cdba04743376410c9f72356b85fb64f
- **Title:** fix(ci_history): do not re-annotate record in the missing-file branch (#4509)
- **Changed Files:**
  1. `scripts/ci_history.py` (8 lines changed: 4 insertions, 4 deletions)
  2. `tests/scripts/test_ci_history.py` (38 lines added)

### Exact Capture Command
```bash
git show 37e230009cdba04743376410c9f72356b85fb64f
```

### Input Identity
- **Repository:** stranske/Workflows
- **Commit SHA:** 37e230009cdba04743376410c9f72356b85fb64f
- **PR Number:** #4509

### Coverage Results
- **scripts/ci_history.py:** Complete extraction with all changes captured (failure_record variable rename)
- **tests/scripts/test_ci_history.py:** Complete extraction with all 38 new lines captured (test_ci_history_type_checks_under_consumer_mypy)
- **Validation:** Both changed files extracted and validated before provider evaluation

### Authenticated GET Evidence
- **Run 42327976097 in trip-planner:** Status=completed, Conclusion=success, Repository=stranske/trip-planner, HeadSHA=948406465cf7cd65d1ac92206b4514aaad455443
- **Run 42327976097 in Workflows:** HTTP 404 (run does not exist in this repository)

## Regression Timing

### Test Execution
- **Test File:** `.github/scripts/agents_verifier_context.cross_repo.test.js`
- **Duration:** < 120 seconds (actual: ~90ms)
- **Status:** All 12 tests passed
- **Exercises:** Both collectors (root and consumer-template)

### Test Coverage
1. ✅ Valid cross-repository evidence extraction
2. ✅ Unavailable evidence handling  
3. ✅ Wrong repository/head detection
4. ✅ Distinct downstream vs current-head provenance
5. ✅ Real-world #4509 URLs
6. ✅ Multiple downstream repositories
7. ✅ Repository mismatch detection
8. ✅ Various URL formats

## Implementation Changes

### Files Modified
1. `.github/scripts/agents_verifier_context.js`
   - Added `extractReferencedRunProvenance()` function
   - Added `WORKFLOW_RUN_URL_WITH_REPO_RE` regex
   - Updated run collection to handle downstream repositories
   - Updated artifact collection to use correct repository context
   - Added `runRepositories` and `downstreamRunProvenance` maps
   - Exported new function

2. `templates/consumer-repo/.github/scripts/agents_verifier_context.js`
   - Applied same changes as root collector
   - Files are byte-identical

3. `.github/scripts/agents_verifier_context.cross_repo.test.js` (NEW)
   - 12 regression tests for cross-repository evidence
   - Tests all required scenarios from issue #4514

## Validation

### Downstream Head Identity vs Current PR-Head Provenance
- **Downstream:** Run 42327976097 in stranske/trip-planner with head_sha 948406465cf7cd65d1ac92206b4514aaad455443
- **Current PR-Head:** Different SHA (not applicable for this downstream run)
- **Distinction:** Downstream runs are tracked separately in `downstreamRunProvenance` map
- **Validation:** Repository mismatch is detected and rejected with provenance failure

### Non-PASS Outcome Retention
- ⚠️ Deliberate missing-file or integrity failures remain non-PASS
- ✅ Run 42327976097 in Workflows returns 404 (unavailable) - non-PASS outcome preserved
- ✅ Consumer result from trip-planner is NOT invalidated by Workflows 404
