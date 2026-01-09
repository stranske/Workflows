# Short-Term Action Plan: LangChain Phase 3 Completion

> **Created:** January 9, 2026  
> **Target Completion:** January 23, 2026 (2 weeks)  
> **Priority:** Complete Phase 3 functional testing and critical fixes

---

## Issue Fixed: Workflows Repo Missing Labels ✅

**Problem:** Agent commands (agents:optimize, etc.) worked on consumer repos but not on Workflows repo itself.

**Root Cause:** The Workflows repo was missing the labels it creates in consumer repos via sync workflow.

**Solution Applied:** Created 8 missing labels:
- `agents:optimize` - Request AI-powered issue analysis
- `agents:formatted` - Issue formatted to template
- `agents:decompose` - Break down large tasks
- `needs-human` - Requires human intervention
- `verify:checkbox` - Verify against acceptance criteria
- `verify:evaluate` - LLM evaluation of merged PR
- `verify:compare` - Multi-model comparison
- `verify:create-issue` - Create follow-up from verification

**Status:** ✅ Fixed - Agent workflows now functional on Workflows repo

---

## Week 1 (January 9-15): Phase 3 Functional Testing

### Priority 1: Execute Test Suites (Days 1-3)

All workflows already deployed to 7 consumer repos. Scripts have 129 passing unit tests. Need functional validation.

**Test Repository:** Manager-Database (primary test bed)

#### Test Suite A: Capability Check
**Workflow:** `agents-capability-check.yml`  
**Test Issues Created:** Manager-Database #227

| Test | Issue Title | Expected Behavior | Success Criteria |
|------|-------------|-------------------|------------------|
| A1 | Integrate Stripe Payment Processing | 🚫 BLOCKED - external API | `needs-human` label added, blocker explanation posted |
| A2 | Add database migration for user roles | 🚫 BLOCKED/⚠️ REVIEW - infrastructure | Flags manual requirement |
| A3 | Refactor logging to structured format | ✅ PROCEED - code-only | No `needs-human`, agent proceeds |

**Execution Steps:**
1. Create 3 test issues in Manager-Database with content from test plan
2. Add `agent:codex` label to each
3. Verify workflow runs and posts capability report
4. Check correct labels applied (`needs-human` for A1/A2, not for A3)
5. Document results in langchain-post-code-rollout.md

#### Test Suite B: Task Decomposition
**Workflow:** `agents-decompose.yml`  
**Test Issues Created:** Manager-Database #228

| Test | Issue Title | Expected Behavior | Success Criteria |
|------|-------------|-------------------|------------------|
| B1 | Implement health check with circuit breaker | 5+ tasks → 4-6 sub-tasks | Clear, actionable breakdown |
| B2 | Add comprehensive API documentation | Many implied tasks → 5-8 sub-tasks | Covers all doc types |
| B3 | Simple: Add version endpoint | 1-2 tasks → minimal split | Doesn't over-decompose |

**Execution Steps:**
1. Create 3 test issues with varying complexity
2. Add `agents:decompose` label
3. Verify sub-task checklist posted as comment
4. Verify label removed after posting
5. Assess quality: Are sub-tasks specific and actionable?

#### Test Suite C: Duplicate Detection
**Workflow:** `agents-dedup.yml`  
**Test Issues Created:** Manager-Database #229

| Test | Issue Title | Similarity To | Expected Result |
|------|-------------|---------------|-----------------|
| C1 | Add GET endpoint for all managers | Existing #133 | ⚠️ DUPLICATE warning |
| C2 | Add PUT endpoint to update manager | Related but different | ✅ NO FLAG |
| C3 | Implement caching layer | Unrelated | ✅ NO FLAG |
| C4 | Get list of all managers from database | Same as C1, different words | ⚠️ DUPLICATE |

**Success Metrics:**
- True positive rate: ≥90% (C1, C4 correctly flagged)
- False positive rate: <10% (C2, C3 not flagged)

**Execution Steps:**
1. Create 4 test issues (automatically triggers workflow)
2. Check for duplicate warning comments
3. Verify correct issues linked
4. Calculate accuracy metrics

#### Test Suite D: Auto-Label
**Workflow:** `agents-auto-label.yml`  
**Test Issues Created:** Manager-Database #230

| Test | Issue Title | Expected Labels |
|------|-------------|-----------------|
| D1 | Fix crash when database connection fails | `bug` |
| D2 | Add support for bulk manager import | `enhancement` |

**Execution Steps:**
1. Create 2 unlabeled issues
2. Verify workflow runs automatically
3. Check if labels suggested/applied
4. Verify accuracy of label matching

**Time Estimate:** 2-3 days (8 issues × 15-20 min each + documentation)

---

### Priority 2: Test Verify-to-Issue (Day 4)

**Workflow:** `agents-verify-to-issue.yml`  
**Status:** Deployed, needs functional test

**Test Plan:**
1. Find merged PR in Travel-Plan-Permission with existing verification comment (e.g., PR #301)
2. Add `verify:create-issue` label
3. Verify:
   - New issue created with CONCERNS extracted
   - Issue has `agents:optimize` label
   - Comment posted on PR linking to issue
   - `verify:create-issue` label removed

**Success Criteria:**
- Issue created with proper context
- Links correct
- Labels applied

**Time Estimate:** 1 hour

---

### Priority 3: Retest agents:apply-suggestions with LLM (Day 5)

**Context:** Configuration changed to `use_llm=True` on January 8, 2026

**Previous Test:** Manager-Database #184
- Quality with `use_llm=False`: 6/10 (structure only, no content)
- Expected with `use_llm=True`: 8.5/10 (intelligent content population)

**Test Plan:**
1. Create new unstructured issue in Manager-Database
2. Add `agents:optimize` label → Review analysis
3. Add `agents:apply-suggestions` label → Check formatted result
4. Compare to previous test:
   - Does it populate Tasks section with analyzed sub-tasks?
   - Does it extract Why/Scope/Non-Goals from context?
   - Are acceptance criteria objective and measurable?

**Success Criteria:**
- Quality score ≥8/10
- All sections populated with intelligent content
- Original content preserved in collapsible

**Time Estimate:** 1 hour

---

## Week 2 (January 16-23): Critical Fixes & Planning

### Priority 4: Resolve Code Conflicts (Days 6-8)

**Remaining Conflicted PRs:** 3 PRs need human/Codex resolution

| Repo | PR # | Title | Conflict Type |
|------|------|-------|---------------|
| Manager-Database | #134 | Add UK Filing Parser Implementation | Real code conflict |
| Manager-Database | #135 | Implement production rate limiter | Real code conflict |
| Portable-Alpha-Extension-Model | #1049 | Codex bootstrap for #1048 | Real code conflict |

**Approach:**
1. Review each PR's conflict
2. Determine if trivial (keepalive auto-resolve) or needs Codex
3. For code conflicts: Add agent label to trigger conflict resolution
4. Verify conflict resolution pipeline works
5. Merge if resolution successful

**Time Estimate:** 2-3 hours (45 min per PR)

---

### Priority 5: Label Cleanup Audit (Days 9-10)

**Goal:** Remove unused/redundant labels from Workflows and consumer repos

**Script Available:** `scripts/cleanup_labels.py` (296 lines)

**Confirmed Bloat Labels to Remove:**
- `codex` (bare) - Redundant with `agent:codex`
- `ai:agent` - Unused variant
- `auto-merge-audit` - Zero matches in codebase
- `automerge:ok` - Unused variant
- `agents:pause` - Consolidated to `agents:paused`

**Execution Plan:**
1. Run audit on Workflows repo first
2. Generate list of idiosyncratic labels per repo
3. Create cleanup PR for Workflows with justification
4. Human approval before execution
5. Repeat for 1-2 consumer repos (Manager-Database, Travel-Plan-Permission)

**Time Estimate:** 3-4 hours

---

### Priority 6: Document Test Results (Days 11-12)

**Deliverables:**
1. Update langchain-post-code-rollout.md with:
   - All 12 test results
   - Accuracy metrics for duplicate detection
   - Quality scores for each workflow
   - Issues encountered and resolutions

2. Create test results summary table:

```markdown
## Phase 3 Functional Test Results

| Workflow | Tests Run | Passed | Failed | Accuracy | Notes |
|----------|-----------|--------|--------|----------|-------|
| agents-capability-check.yml | 3 | X | X | X% | ... |
| agents-decompose.yml | 3 | X | X | N/A | ... |
| agents-dedup.yml | 4 | X | X | X% | ... |
| agents-auto-label.yml | 2 | X | X | X% | ... |
```

3. Update SHORT_TERM_PLAN.md with actual vs. expected results

**Time Estimate:** 2 hours

---

### Priority 7: Plan Phase 4 Rollout (Days 13-14)

**Objectives:**
1. Review Phase 3 results and identify improvements
2. Design Auto-Pilot workflow (4C) state machine
3. Draft User Guide outline (4B)
4. Prioritize remaining Phase 4 components

**Specific Tasks:**

**7A. Auto-Pilot Design Session**
- Map sequential workflow triggers
- Define safety limits:
  - Max keepalive iterations: 10
  - Token budget per issue: 100K
  - Human approval gates
- Design failure handling and rollback mechanism
- Create `agents:auto-pilot-pause` label logic

**7B. User Guide Outline**
Create structure for `docs/WORKFLOW_USER_GUIDE.md`:
- Quick start (3 most common flows)
- Label decision tree
- Troubleshooting section
- Advanced: Combining workflows

**7C. Risk Assessment**
Evaluate risks for:
- Runaway automation (auto-pilot)
- CI instability blocking automation
- LLM token exhaustion
- False positive duplicate closures

**Time Estimate:** 4-5 hours

---

## Success Criteria for 2-Week Plan

### Must Complete (Blockers for Phase 4)
- [ ] 12/12 Phase 3 functional tests executed
- [ ] Test results documented
- [ ] agents:apply-suggestions with LLM retested
- [ ] 3 conflicted PRs resolved

### Should Complete (High Value)
- [ ] Verify-to-issue workflow tested
- [ ] Label cleanup on Workflows repo
- [ ] Phase 4 design document created

### Nice to Have (If Time Permits)
- [ ] Label cleanup on 2 consumer repos
- [ ] User guide outline drafted
- [ ] Auto-pilot state machine diagram

---

## Risk Mitigation

### Risk 1: Tests Reveal Critical Issues
**Mitigation:** 
- Document issues immediately
- Create fix PRs before continuing
- Re-sync consumer repos if workflow fixes needed

### Risk 2: Conflict Resolution Doesn't Work
**Mitigation:**
- Manual resolution as fallback
- Document specific conflict patterns
- Update conflict_detector.js if needed

### Risk 3: Time Overruns
**Mitigation:**
- Focus on must-complete items first
- Defer label cleanup to Week 3 if needed
- Phase 4 planning can extend beyond 2 weeks

---

## Daily Standup Template

```markdown
## Day X Progress

**Completed:**
- [ ] Test Suite X
- [ ] Issue Y resolved

**In Progress:**
- [ ] Test Suite Z (blocked on...)

**Blockers:**
- None / [describe blocker]

**Next Steps:**
- [ ] Item 1
- [ ] Item 2
```

---

## Tracking

### Week 1 Checklist
- [ ] Day 1: Test Suite A (Capability Check)
- [ ] Day 2: Test Suite B (Task Decomposition)
- [ ] Day 3: Test Suite C (Duplicate Detection) + Suite D (Auto-Label)
- [ ] Day 4: Test Verify-to-Issue workflow
- [ ] Day 5: Retest agents:apply-suggestions with LLM

### Week 2 Checklist
- [ ] Day 6-8: Resolve 3 conflicted PRs
- [ ] Day 9-10: Label cleanup audit
- [ ] Day 11-12: Document test results
- [ ] Day 13-14: Plan Phase 4 rollout

---

## Post-Plan: Phase 4 Preview

**After 2-week plan completion, focus shifts to:**

1. **Auto-Pilot Implementation** (High risk, careful testing)
   - Create `agents-auto-pilot.yml` orchestrator
   - Test on simple issues only
   - Add safety mechanisms

2. **User Guide** (Documentation)
   - Full WORKFLOW_USER_GUIDE.md
   - Add to all consumer repos

3. **Metrics Dashboard** (Visibility)
   - LangSmith integration for LLM metrics
   - Custom GitHub metrics collection
   - Weekly summary reports

**Timeline:** Phase 4 estimated 3-4 weeks after Phase 3 completion

---

## Related Documents

- Full rollout plan: [langchain-post-code-rollout.md](langchain-post-code-rollout.md)
- Test plan details: langchain-post-code-rollout.md sections "Phase 3 Functional Testing"
- Label documentation: [LABELS.md](../LABELS.md)

---

## Questions & Decisions

**Q: Should we test on multiple consumer repos or just Manager-Database?**  
**A:** Manager-Database primary, Travel-Plan-Permission for verify-to-issue. Sufficient for validation.

**Q: What if duplicate detection has >10% false positive rate?**  
**A:** Add confidence threshold parameter, increase from 85% to 90%. Retest.

**Q: Should we disable workflows if tests fail?**  
**A:** No - workflows are comment/label-only, no destructive actions. Fix forward instead.
