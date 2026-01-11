# Short-Term Plan Summary

> **Status:** Historical snapshot (plan + early execution notes)
> **Created:** 2026-01-09
> **Last reviewed:** 2026-01-11
> **Canonical references:** `docs/ci/WORKFLOW_SYSTEM.md` (workflow inventory), `docs/validation/overview.md` (local validation)

**Timeline:** 2 weeks (January 9-23, 2026)

---

## Critical Issue Fixed ✅

**Problem Identified:** Agent commands (agents:optimize, etc.) worked on consumer repos but not on Workflows repo itself.

**Root Cause:** Workflows repo was missing the labels it creates in consumer repos via sync workflow.

**Solution Applied:** Created 8 missing labels in Workflows repo:
- ✅ `agents:optimize` - Request AI-powered issue analysis
- ✅ `agents:formatted` - Issue formatted to template  
- ✅ `agents:decompose` - Break down large tasks
- ✅ `needs-human` - Requires human intervention
- ✅ `verify:checkbox` - Verify against acceptance criteria
- ✅ `verify:evaluate` - LLM evaluation of merged PR
- ✅ `verify:compare` - Multi-model comparison
- ✅ `verify:create-issue` - Create follow-up from verification

**Current Status:** All 16 agent-related labels now present in Workflows repo. Agent workflows now functional.

---

## 2-Week Plan Overview

### Week 1: Phase 3 Functional Testing
**Focus:** Execute functional tests across new workflows

| Day | Activity | Deliverable |
|-----|----------|-------------|
| 1 | Test Suite A: Capability Check (3 tests) | Manager-Database #227 |
| 2 | Test Suite B: Task Decomposition (3 tests) | Manager-Database #228 |
| 3 | Test Suite C: Duplicate Detection (4 tests) + Suite D: Auto-Label (2 tests) | Manager-Database #229, #230 |
| 4 | Test Verify-to-Issue workflow | Travel-Plan-Permission test |
| 5 | Retest agents:apply-suggestions with LLM enabled | Manager-Database new issue |

### Week 2: Critical Fixes & Planning
**Focus:** Resolve blockers and prepare Phase 4

| Day | Activity | Deliverable |
|-----|----------|-------------|
| 6-8 | Resolve 3 conflicted PRs | Manager-Database #134, #135; Portable-Alpha-Extension-Model #1049 |
| 9-10 | Label cleanup audit | Workflows repo cleanup PR |
| 11-12 | Document all test results | Updated langchain-post-code-rollout.md |
| 13-14 | Design Phase 4 components | Auto-pilot state machine, user guide outline |

---

## Success Criteria

### Must Complete (Blockers)

These were the intended success criteria at the time. For the final state and evidence, see `SHORT_TERM_PLAN.md`.

- [ ] Phase 3 functional tests executed and documented
- [ ] agents:apply-suggestions with LLM retested
- [ ] Conflicted PRs resolved

### Should Complete (High Value)
- [ ] Verify-to-issue workflow tested
- [ ] Label cleanup on Workflows repo
- [ ] Phase 4 design document

### Nice to Have
- [ ] Label cleanup on 2 consumer repos
- [ ] User guide outline
- [ ] Auto-pilot state machine diagram

---

## Test Execution Summary

### Phase 3 Workflows to Test (All Deployed to 7 Repos)

| Workflow | Tests | Test Issues Created | Status |
|----------|-------|---------------------|--------|
| `agents-capability-check.yml` | 3 | Manager-Database #227 | See `SHORT_TERM_PLAN.md` |
| `agents-decompose.yml` | 3 | Manager-Database #228 | See `SHORT_TERM_PLAN.md` |
| `agents-dedup.yml` | 4 | Manager-Database #229 | See `SHORT_TERM_PLAN.md` |
| `agents-auto-label.yml` | 2 | Manager-Database #230 | See `SHORT_TERM_PLAN.md` |
| `agents-verify-to-issue.yml` | 1 | Travel-Plan-Permission PR | See `SHORT_TERM_PLAN.md` |

**Total Tests:** 13 functional tests (12 Phase 3 + 1 Phase 4E)

---

## Key Documents

- **Full Plan:** [SHORT_TERM_PLAN.md](SHORT_TERM_PLAN.md) - Detailed 2-week execution plan
- **Rollout Status:** [langchain-post-code-rollout.md](langchain-post-code-rollout.md) - Complete Phase 1-4 status
- **Label Reference:** [LABELS.md](../LABELS.md) - All functional labels

---

## Next Actions (Immediate)

This section is kept for historical context. Follow the current runbooks and workflow docs instead of treating it as a live checklist.

---

## Related Context

**Previous Work Completed:**
- ✅ All Phase 3 workflows deployed to 7 consumer repos (2026-01-09)
- ✅ Conflict resolution pipeline deployed (2026-01-09)
- ✅ 129 unit tests passing for Phase 3 scripts
- ✅ Phase 1 & 2 workflows tested in production

**Remaining Work:** Phase 3 functional validation + Phase 4 implementation

**Timeline to Phase 4:** ~3 weeks (2 weeks testing + 1 week fixes/planning)
