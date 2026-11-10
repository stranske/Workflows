# Issue #4522 Verification Summary

This document records the execution of the three commands specified in issue #4522 and their results.

## Command 1: Verify PR #2390 Merge Status

**Command:**
```bash
gh pr view 2390 --repo stranske/Portable-Alpha-Extension-Model --json state,mergedAt
```

**Result:**
```json
{"mergedAt":null,"state":"CLOSED"}
```

**Analysis (re-checked 2026-11-09):**
The literal criterion is **not met**: PR #2390 is `CLOSED` with `mergedAt: null`
(`closedAt` 2026-11-07T08:17:51Z). An earlier version of this summary claimed that
`f1b18898fd5fd1ecabe29c4682e5a395962c70e2` landed PR #2390 on `main`. That claim was
wrong and is withdrawn. `f1b1889` ("Merge 09298cf6... into c3190d76...", 2026-11-05T05:38:53Z)
is GitHub's synthetic PR test-merge commit, and it is not on the default branch:

```bash
gh api repos/stranske/Portable-Alpha-Extension-Model/compare/main...f1b18898fd5fd1ecabe29c4682e5a395962c70e2 \
  --jq '{status,ahead_by,behind_by}'
# {"ahead_by":2,"behind_by":7,"status":"diverged"}
```

**Equivalent integration on the default branch:**

```bash
gh api repos/stranske/Portable-Alpha-Extension-Model/commits --method GET \
  -f path=.github/workflows/pr-00-gate.yml
```

The newest default-branch commit touching `pr-00-gate.yml` is
`693037352463bb4d4db215144aaa9f2d2eb3a224`,
"fix(ci): remove labeled Gate trigger (Workflows#4082 campaign) (#2456)", committed
2026-11-02T17:02:33Z. It has a single parent (`5b96b765`), so it is a squash merge.

- `gh pr view 2456 --repo stranske/Portable-Alpha-Extension-Model --json state,mergedAt,mergeCommit`
  returns `MERGED`, `mergedAt` **2026-11-02T17:02:34Z**, and `mergeCommit` `69303735`.
- Ancestry: `compare/69303735...main` returns `{"status":"ahead","ahead_by":20,"behind_by":0}`
  with `main` at `c8a67be5` (read 2026-11-09), so the commit is an ancestor of `main`.
- Its `pr-00-gate.yml` hunk is the same one-line change as PR #2390:
  `types: [opened, synchronize, reopened, ready_for_review, labeled]` becomes
  `types: [opened, synchronize, reopened, ready_for_review]`. It also adds
  `tests/workflows/test_gate_pull_request_triggers.py` and a test-isolation edit.
- The current `main` file has `types: [opened, synchronize, reopened, ready_for_review]`.

**Conclusion:** The campaign change for Portable-Alpha-Extension-Model reached `main` on
2026-11-02T17:02:34Z through PR #2456, not through PR #2390. That is an equivalent
integration. The literal acceptance criterion ("PR #2390 `state` is `MERGED`") stays
**unmet**: no API result shows PR #2390 as merged, and none will, because the PR was
closed without merging.

**Final campaign integration timestamp:** live `gh pr view` checks (2026-11-09) show the
other 13 campaign PRs `MERGED` between 2026-10-18T07:55:16Z and 2026-10-18T14:51:47Z
(the latest is Ready#633). PAEM#2456 at **2026-11-02T17:02:34Z** is therefore the
final campaign integration. That timestamp anchors the observation below.

## Command 2: Drift Check

**Command:**
```bash
python3 scripts/check_consumer_sync_drift.py \
  --repos stranske/Counter_Risk,stranske/Deliverable-Render,stranske/Doc-Lineage,stranske/Fine-Art-Archive,stranske/Inv-Man-Intake,stranske/Manager-Mosaic,stranske/Orchestrator,stranske/Pension-Data,stranske/Portable-Alpha-Extension-Model,stranske/Ready,stranske/Travel-Plan-Permission,stranske/Trend_Model_Project,stranske/learning-management-system,stranske/trip-planner \
  --report-json docs/evidence/issue-4082/drift-report-post-merge.json
```

**Result:**
```
gate triggers: all match
Consumer repos are in sync.
```

**Verification:**
- ✅ stdout contains 'gate triggers: all match'
- ✅ report-json written to docs/evidence/issue-4082/drift-report-post-merge.json
- ✅ All 14 consumer repos verified with no drift
- ✅ No errors (previously failed due to missing authentication)

**Note:** The script now runs successfully with GH_TOKEN authentication available in the environment.

## Command 3: 48-hour Gate Cancellation Observation

**Command:**
```bash
FINAL_CAMPAIGN_MERGED_AT=2026-11-02T17:02:34Z   # PAEM#2456 mergedAt; see Command 1
/opt/anaconda3/bin/python3 scripts/measure_gate_cancellations.py \
  --merge "$FINAL_CAMPAIGN_MERGED_AT" \
  --output docs/evidence/issue-4082/observation-evidence-final.json
```

**Result (exit 0, 19 s):**
```json
{
  "collected_at": "2026-11-09T12:19:16Z",
  "interval_start": "2026-11-02T17:02:34Z",
  "interval_end": "2026-11-04T17:02:34Z",
  "repos": ["stranske/Travel-Plan-Permission", "stranske/Template", "stranske/Counter_Risk", "stranske/Pension-Data", "stranske/Inv-Man-Intake", "stranske/Ready", "stranske/trip-planner", "stranske/Manager-Database", "stranske/Portable-Alpha-Extension-Model", "stranske/Trend_Model_Project", "stranske/learning-management-system", "stranske/Fine-Art-Archive", "stranske/Orchestrator", "stranske/Doc-Lineage", "stranske/Deliverable-Render", "stranske/Manager-Mosaic"],
  "errors": {},
  "numerator": 0,
  "denominator": 401,
  "percentage": 0.0,
  "passed": true,
  "status": "complete"
}
```

**What the metric measures:** `numerator` comes from
`scripts/measure_gate_cancellations.py::counts`. It counts only **qualifying
duplicate-trigger cancellations**: `pull_request` Gate runs that ended `cancelled` and have
a different run on the same head SHA created within 5 seconds (the immediate neighbour
before or after, in creation order). It is **not** the count of all cancelled runs, and
0.0% is **not** an overall cancellation rate.

**Verification (recounted from the committed `runs` with `counts`):**
- ✅ `status` is `complete`, and `errors` is `{}`
- ✅ The complete 48-hour window 2026-11-02T17:02:34Z → 2026-11-04T17:02:34Z starts at the
  verified final integration, and the window had ended before collection
- ✅ `counts()` recomputation gives `(0, 401)`, which matches the stored numerator and denominator
- ✅ 0 qualifying duplicate-trigger cancellations out of 401 Gate runs (0.0% ≤ 5.0)
- ℹ️ All cancellations: **21 of 401** runs ended `cancelled` (16 `pull_request`, 5 `push`;
  Orchestrator 14, Ready 6, trip-planner 1). None met the ≤5 s same-head sibling condition.

**Superseded, unanchored dataset (kept for reference):** the earlier run used the
synthetic `f1b1889` timestamp (2026-11-05T05:38:53Z → 2026-11-07T05:38:53Z). It is kept as
`observation-evidence-unanchored-f1b1889.json`. It recounts to `(0, 476)` with `counts()`,
which means 0 qualifying duplicate-trigger cancellations, but **30 of 476** runs ended
`cancelled` (25 `pull_request`, 5 `push`). Its window does not start at a verified
integration, so it does not support acceptance.

## Acceptance Criteria Status

1. **❌ Literal criterion unmet. Equivalent integration is verified.**
   - `gh pr view 2390` returns `CLOSED` with `mergedAt: null`. The required `MERGED` result was not obtained.
   - The same `pr-00-gate.yml` change reached `main` through PAEM#2456 (`69303735`, `mergedAt`
     2026-11-02T17:02:34Z, an ancestor of `main` `c8a67be5`).
   - Accepting PR #2456 in place of PR #2390 is an owner/judge decision. This summary does not mark the literal criterion as met.

2. **✅ Drift check output contains 'gate triggers: all match':**
   - stdout contains 'gate triggers: all match'
   - All 14 consumer repos show no drift. The report is `docs/evidence/issue-4082/drift-report-post-merge.json`

3. **✅ Cancellation observation complete with percentage ≤ 5.0, anchored to the verified final integration:**
   - `status` is `complete`, `errors` is `{}`, `percentage` is 0.0, and `passed` is true
   - Window 2026-11-02T17:02:34Z → 2026-11-04T17:02:34Z (PAEM#2456 `mergedAt`)
   - The metric is qualifying duplicate-trigger cancellations (0/401). Total cancelled runs were 21/401.

## Conclusion

- **Integration:** the campaign trigger change is on every consumer's default branch. For
  PAEM it arrived through PR #2456 on 2026-11-02T17:02:34Z. PR #2390 itself was closed
  unmerged, so the literal "PR #2390 MERGED" criterion is **not met**.
- **Drift:** 'gate triggers: all match' across all 14 consumer repos.
- **Observation:** a complete 48-hour window after the verified final integration shows 0
  qualifying duplicate-trigger cancellations out of 401 Gate runs (0.0% ≤ 5.0). 21 runs in
  that window were cancelled for other reasons. They are not duplicate-trigger restarts as
  `counts()` defines them.

Issue #4522 is complete on its substance (drift and observation). The literal PR-status
criterion remains unmet unless PR #2456 is accepted as the equivalent integration.
