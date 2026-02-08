# Auto-Pilot Remediation Plan

> **⚠️ SUPERSEDED (Feb 2026):** Most remediations here have been implemented.
> See [`autopilot-40pr-evaluation-feb-2026.md`](./autopilot-40pr-evaluation-feb-2026.md)
> for the current evaluation and remaining recommendations (P0-P3).

**Created:** 2026-01-15  
**Purpose:** Action plan to address design deviations in agents:auto-pilot workflow  
**Related:** [Deviations Summary](./autopilot-deviations-summary.md), [Full Evaluation](./autopilot-design-compliance-evaluation.md)  
**Status:** READY FOR APPROVAL

---

## Executive Summary

This plan provides **three options** for addressing the 10 identified deviations in agents:auto-pilot workflow, ranging from minimal changes to full architectural refactoring.

**Recommended Approach:** **Option 2 (Hybrid)** - Quick wins now, refactor later

---

## Option 1: Minimal (Accept Current Design)

**Philosophy:** Auto-pilot's inline architecture is acceptable. Fix only critical safety issues.

### Why Choose This
- ✅ Lowest effort (2-3 days)
- ✅ Minimal risk
- ✅ Gets metrics working quickly
- ❌ Doesn't fix architectural debt
- ❌ Documentation still mismatches code

### Tasks

#### 1. Fix Critical Safety Issues (HIGH PRIORITY)

**Add Run Cap Enforcement:**
```yaml
# In agents-auto-pilot.yml, before re-dispatch (around line 1039)
- name: Check concurrent run limit
  id: check_concurrent
  run: |
    # Count active auto-pilot runs for this issue
    count=$(gh api "/repos/${{ github.repository }}/actions/workflows/agents-auto-pilot.yml/runs" \
      --jq '[.workflow_runs[] | 
             select(.status == "queued" or .status == "in_progress") | 
             select(.display_title | contains("#${{ steps.context.outputs.issue_number }}"))] | 
             length')
    
    max_concurrent=3  # Default cap
    
    if [ "$count" -ge "$max_concurrent" ]; then
      echo "⚠️ Run cap reached: $count active runs for issue #${{ steps.context.outputs.issue_number }}"
      echo "exceeded=true" >> "$GITHUB_OUTPUT"
    else
      echo "exceeded=false" >> "$GITHUB_OUTPUT"
    fi

- name: Re-dispatch for next step
  if: steps.check_concurrent.outputs.exceeded != 'true'
  # ... existing re-dispatch code
```

**Add Pause Label Support:**
```yaml
# In "Determine context" step (around line 230)
if (labels.includes('agents:paused') || labels.includes('agents:auto-pilot-pause')) {
  core.info('Auto-pilot paused by pause label');
  core.setOutput('should_continue', 'false');
  core.setOutput('reason', 'paused');
  return;
}
```

**Estimated Effort:** 4 hours  
**Risk:** Low  
**PR Size:** ~50 lines

---

#### 2. Implement Metrics (ISSUE #880)

Use [revised scope](./issue-880-revised-scope.md):

1. Create `scripts/autopilot_metrics.py`
2. Wrap inline steps with timing
3. Emit NDJSON metrics to workflow logs
4. Document schema

**Estimated Effort:** 1-2 days  
**Risk:** Low (observability only)  
**PR Size:** ~300 lines (script + workflow changes + docs)

---

#### 3. Update Documentation

Create `docs/architecture/auto-pilot-design.md`:
```markdown
# Auto-Pilot Architecture (Current Implementation)

## Overview
Auto-pilot is a **monolithic workflow** that runs issue preparation steps inline,
then hands off to keepalive for PR work.

## Why Inline Execution
After 32 PRs addressing race conditions and label interference (see AUTOPILOT_FIX_HISTORY.md),
the workflow evolved to run formatters/optimizers inline rather than dispatching separate workflows.

This trades observability for reliability.

## Architecture Diagram
[Include actual flow: label → inline format → inline optimize → inline apply → agent label → PR creation → keepalive handoff]

## Differences from Design Docs
Design docs (GoalsAndPlumbing.md, SHORT_TERM_PLAN.md) describe an orchestrator pattern.
Current implementation is monolithic. Both are valid; this is what we actually built.
```

Mark aspirational sections in other docs:
```markdown
<!-- ASPIRATIONAL: Current implementation differs. See docs/architecture/auto-pilot-design.md -->
```

**Estimated Effort:** 4 hours  
**Risk:** None  
**PR Size:** ~200 lines

---

### Option 1 Summary

| Task | Effort | Risk | PR Size |
|------|--------|------|---------|
| Safety fixes (run cap, pause label) | 4 hours | Low | ~50 lines |
| Metrics implementation | 1-2 days | Low | ~300 lines |
| Documentation update | 4 hours | None | ~200 lines |
| **TOTAL** | **2-3 days** | **Low** | **~550 lines** |

**Outcome:** Safe, observable, but architecturally unchanged

---

## Option 2: Hybrid (Recommended)

**Philosophy:** Fix critical issues now, refactor architecture later in phases.

### Why Choose This
- ✅ Addresses safety immediately
- ✅ Gets metrics working
- ✅ Sets foundation for future refactoring
- ✅ Iterative, low risk per phase
- ⚠️ Medium effort overall
- ⚠️ Requires sustained investment

### Phase 1: Safety & Observability (Week 1)

Same as Option 1:
1. ✅ Add run cap enforcement
2. ✅ Add pause label support
3. ✅ Implement metrics (revised #880)
4. ✅ Update docs

**Effort:** 2-3 days  
**Outcome:** Safe and observable

---

### Phase 2: Separation Prep (Week 2-3)

Extract inline logic to standalone scripts for testability:

**Create `scripts/autopilot_steps.py`:**
```python
#!/usr/bin/env python3
"""Auto-pilot step implementations."""

def run_format_step(issue_number: int, github_token: str) -> dict:
    """Format issue, return metrics."""
    start = time.time()
    try:
        # Existing format logic from workflow
        result = format_issue(issue_number, github_token)
        return {
            "outcome": "success",
            "duration_ms": int((time.time() - start) * 1000)
        }
    except Exception as e:
        return {
            "outcome": "failure",
            "duration_ms": int((time.time() - start) * 1000),
            "error": str(e)
        }

def run_optimize_step(issue_number: int, github_token: str, openai_key: str) -> dict:
    """Run optimizer, return metrics."""
    # Similar pattern

def run_apply_step(issue_number: int, github_token: str) -> dict:
    """Apply suggestions, return metrics."""
    # Similar pattern
```

**Update workflow to call scripts:**
```yaml
- name: Execute step - Format
  run: |
    python scripts/autopilot_steps.py format \
      --issue "$ISSUE_NUMBER" \
      --github-token "$GITHUB_TOKEN" \
      --json > /tmp/result.json
    
    outcome=$(jq -r '.outcome' /tmp/result.json)
    if [ "$outcome" != "success" ]; then exit 1; fi
```

**Benefits:**
- Scripts are unit testable
- Logic separated from workflow plumbing
- Foundation for extracting to workflows later

**Estimated Effort:** 3-4 days  
**Risk:** Medium (refactoring existing code)  
**PR Size:** ~400 lines

---

### Phase 3: Workflow Separation (Week 4-5)

Convert scripts to reusable workflows:

**Create `.github/workflows/reusable-issue-format.yml`:**
```yaml
name: Reusable Issue Format

on:
  workflow_call:
    inputs:
      issue_number:
        required: true
        type: number
    outputs:
      outcome:
        description: "success or failure"
        value: ${{ jobs.format.outputs.outcome }}
      duration_ms:
        description: "Execution time in milliseconds"
        value: ${{ jobs.format.outputs.duration_ms }}

jobs:
  format:
    runs-on: ubuntu-latest
    outputs:
      outcome: ${{ steps.run.outputs.outcome }}
      duration_ms: ${{ steps.run.outputs.duration_ms }}
    steps:
      - uses: actions/checkout@v6
      - name: Run format
        id: run
        run: |
          python scripts/autopilot_steps.py format \
            --issue "${{ inputs.issue_number }}" \
            --github-token "${{ secrets.GITHUB_TOKEN }}" \
            --json > /tmp/result.json
          
          jq -r 'to_entries | .[] | "\(.key)=\(.value)"' /tmp/result.json >> "$GITHUB_OUTPUT"
```

**Update auto-pilot to call workflows:**
```yaml
format-issue:
  if: steps.next.outputs.next_step == 'format'
  uses: ./.github/workflows/reusable-issue-format.yml
  with:
    issue_number: ${{ steps.context.outputs.issue_number }}

optimize-issue:
  if: steps.next.outputs.next_step == 'optimize'
  needs: format-issue
  uses: ./.github/workflows/reusable-issue-optimize.yml
  with:
    issue_number: ${{ steps.context.outputs.issue_number }}
```

**Benefits:**
- Proper workflow boundaries
- Each step has own observability
- Reusable in other contexts

**Estimated Effort:** 1 week  
**Risk:** Medium-high (changes execution model)  
**PR Size:** ~600 lines

---

### Phase 4: Observability Contract (Week 6)

Implement `DISPATCH:` / `INSTRUCTION:` / `WORKER:` summaries:

**In auto-pilot orchestrator:**
```yaml
- name: Emit dispatch summary
  run: |
    echo "DISPATCH: ok=true path=label reason=ok issue=#${{ steps.context.outputs.issue_number }} step=${{ steps.next.outputs.next_step }}"
```

**In reusable workflows:**
```yaml
- name: Emit instruction summary
  run: |
    echo "INSTRUCTION: ok=true workflow=format issue=#${{ inputs.issue_number }}"

- name: Emit worker summary
  run: |
    echo "WORKER: action=execute step=format outcome=${{ steps.run.outputs.outcome }}"
```

**Benefits:**
- Matches documented contract
- Parseable logs
- Unified with keepalive observability

**Estimated Effort:** 2-3 days  
**Risk:** Low (pure logging)  
**PR Size:** ~100 lines

---

### Option 2 Summary

| Phase | Effort | Risk | Outcome |
|-------|--------|------|---------|
| 1. Safety & Observability | 2-3 days | Low | Safe + metrics |
| 2. Separation Prep | 3-4 days | Medium | Testable scripts |
| 3. Workflow Separation | 1 week | Medium-High | Proper boundaries |
| 4. Observability Contract | 2-3 days | Low | Documented compliance |
| **TOTAL** | **3-4 weeks** | **Medium** | **Fully compliant** |

**Outcome:** Gradual migration to intended design, each phase delivers value

---

## Option 3: Full Refactor (All at Once)

**Philosophy:** Rebuild auto-pilot to match original design in one go.

### Why Choose This
- ✅ Fastest path to compliance
- ✅ Clean slate, no incremental debt
- ❌ Highest risk (big bang change)
- ❌ Long feature freeze (~2 weeks)
- ❌ Hard to roll back if issues

### Approach

1. **Week 1: Design & Prep**
   - Finalize workflow interfaces
   - Write tests for current behavior
   - Create migration plan

2. **Week 2: Implementation**
   - Create all reusable workflows
   - Implement observability contract
   - Add run cap, pause controls
   - Wire up auto-pilot orchestrator

3. **Week 3: Testing & Migration**
   - Integration tests
   - Deploy to test repo
   - Fix issues
   - Deploy to production

### Risks

- Breaking changes to active PRs
- Unforeseen integration issues
- Team velocity halts for 2-3 weeks
- Rollback complexity

**Estimated Effort:** 2-3 weeks  
**Risk:** High  
**PR Size:** ~1500 lines (multiple PRs)

---

## Comparison Matrix

| Criterion | Option 1: Minimal | Option 2: Hybrid | Option 3: Full Refactor |
|-----------|------------------|------------------|------------------------|
| **Effort** | 2-3 days | 3-4 weeks (phased) | 2-3 weeks (all at once) |
| **Risk** | Low | Medium (per phase) | High |
| **Time to Safe** | 4 hours | 4 hours | 2-3 weeks |
| **Time to Metrics** | 2-3 days | 2-3 days | 2-3 weeks |
| **Design Compliance** | 10% → 30% | 10% → 100% (gradual) | 10% → 100% (immediate) |
| **Rollback Cost** | None | Per phase | High |
| **Team Disruption** | Minimal | Low (phased) | High (2-3 week freeze) |
| **Architectural Debt** | Remains | Eliminated | Eliminated |

---

## Recommended Path: Option 2 (Hybrid)

### Why Hybrid Wins

1. **Immediate Safety:** Phase 1 fixes critical issues in 4 hours
2. **Quick Metrics:** Phase 1 delivers #880 in 2-3 days
3. **Incremental Risk:** Each phase is independently valuable and revertible
4. **Team Velocity:** No long feature freeze
5. **Learning:** Each phase informs the next

### Execution Strategy

**Month 1:**
- Week 1: Phase 1 (safety + metrics) ✅ CRITICAL
- Week 2-3: Phase 2 (script extraction) ⚠️ IMPORTANT
- Week 4: Buffer/planning

**Month 2:**
- Week 1-2: Phase 3 (workflow separation) ⚠️ IMPORTANT
- Week 3: Phase 4 (observability) 
- Week 4: Testing, docs, cleanup

**Success Criteria per Phase:**

| Phase | Entry Criteria | Exit Criteria | Rollback Plan |
|-------|---------------|---------------|---------------|
| 1 | None | Run cap works, metrics emit, docs updated | Revert PR |
| 2 | Phase 1 complete | Scripts pass unit tests, workflow still works | Keep scripts, revert workflow changes |
| 3 | Phase 2 complete | Workflows callable independently, auto-pilot works | Use scripts inline temporarily |
| 4 | Phase 3 complete | Summaries parseable, match contract | Phase 4 optional, no rollback needed |

---

## Alternative: Skip to Option 1, Defer Refactor

If timeline is critical:

1. **Do Option 1 now** (2-3 days)
2. **Create "Auto-Pilot v2" planning issue** with Option 2 phases
3. **Schedule for Q2 2026**

This gives:
- ✅ Safe + observable immediately
- ✅ Time to evaluate metrics before refactoring
- ✅ No rush on architectural changes
- ❌ Architectural debt persists longer

---

## Task Breakdown (Option 2, Phase 1)

### Critical Safety Fixes

**File:** `.github/workflows/agents-auto-pilot.yml`

1. **Add run cap check** (before line 1039):
   ```yaml
   - name: Check concurrent run limit
     id: check_concurrent
     # ... implementation from Option 1 above
   ```

2. **Update re-dispatch condition** (line 1040):
   ```yaml
   if: |
     steps.context.outputs.should_continue == 'true' &&
     steps.cycles.outputs.exceeded != 'true' &&
     steps.check_concurrent.outputs.exceeded != 'true' &&  # NEW
     contains(fromJSON('["format","optimize","apply","capability-check","monitor-pr"]'),
     steps.next.outputs.next_step)
   ```

3. **Add pause label check** (line 230):
   ```yaml
   if (labels.includes('agents:paused') || labels.includes('agents:auto-pilot-pause')) {
     // ... pause logic
   }
   ```

**Estimated Lines Changed:** ~50

---

### Metrics Implementation

**New File:** `scripts/autopilot_metrics.py` (~150 lines)

**Updates to:** `.github/workflows/agents-auto-pilot.yml` (~150 lines)
- Emit cycle-start after "Determine next step"
- Wrap each step with timing
- Emit cycle-end before re-dispatch
- Emit summary on done/failed

**New File:** `docs/metrics/autopilot-metrics-schema.md` (~100 lines)

**Estimated Lines Added:** ~400

---

### Documentation

**New File:** `docs/architecture/auto-pilot-design.md` (~200 lines)
- Explain monolithic architecture
- Diagram actual flow
- Justify inline execution
- Acknowledge differences from design docs

**Updates:**
- `docs/keepalive/GoalsAndPlumbing.md`: Add note about auto-pilot deviation
- `docs/plans/SHORT_TERM_PLAN.md`: Mark orchestrator description as aspirational
- `README.md`: Link to architecture doc

**Estimated Lines Added:** ~250

---

## Implementation Order (Phase 1)

```
Day 1 Morning:
  ├─ Add run cap check (2 hours)
  ├─ Add pause label support (1 hour)
  └─ Test on staging (1 hour)

Day 1 Afternoon:
  ├─ Create metrics script skeleton (2 hours)
  ├─ Add unit tests (1 hour)
  └─ Emit first metric (cycle-start) (1 hour)

Day 2 Morning:
  ├─ Wrap format step with timing (1 hour)
  ├─ Wrap optimize step with timing (1 hour)
  ├─ Wrap apply step with timing (1 hour)
  └─ Test metrics output (1 hour)

Day 2 Afternoon:
  ├─ Emit cycle-end and summary metrics (2 hours)
  ├─ Document metrics schema (1 hour)
  └─ Integration test (1 hour)

Day 3:
  ├─ Write architecture doc (3 hours)
  ├─ Update related docs (2 hours)
  ├─ Final testing (2 hours)
  └─ Create PR (1 hour)
```

**Total:** 3 days (24 hours) for Phase 1

---

## Acceptance Criteria

### Phase 1 Complete When:

- [ ] Run cap check prevents >3 concurrent auto-pilot runs for same issue
- [ ] `agents:paused` label pauses auto-pilot
- [ ] Metrics emitted for every cycle:
  - [ ] cycle-start
  - [ ] step (format, optimize, apply)
  - [ ] cycle-end
  - [ ] summary (on done/failed)
- [ ] Metrics are valid NDJSON, parseable with `jq`
- [ ] Documentation explains:
  - [ ] Why inline architecture was chosen
  - [ ] How current design differs from docs
  - [ ] What metrics are available
- [ ] All tests pass
- [ ] Issue #880 can be closed

---

## Risk Mitigation

### For Phase 1

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Run cap breaks re-dispatch | Low | High | Test with manual dispatch, verify count logic |
| Metrics spam logs | Medium | Low | Use structured NDJSON, one line per event |
| Inline timing adds overhead | Low | Low | Timing is microseconds, negligible |
| Docs contradict code | High | Medium | Clearly mark aspirational vs actual |

### For Later Phases

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Workflow separation breaks active PRs | Medium | High | Deploy during quiet period, have rollback ready |
| Performance regression | Low | Medium | Benchmark before/after |
| Integration issues | Medium | Medium | Extensive testing in staging repo |

---

## Success Metrics

### Phase 1 Success Metrics

- Auto-pilot runs without exceeding cap (0 cap violations)
- Metrics logged for 100% of cycles
- No increase in failure rate
- Operators can parse metrics to answer: "Which step takes longest?"

### Long-Term Success Metrics (All Phases)

- 100% compliance with design docs
- <5 minute per-step execution time
- Reusable workflows used in 2+ contexts
- Zero architectural debt items

---

## Next Steps

1. **User Decision:**
   - Choose Option 1, 2, or 3
   - Approve Phase 1 scope
   - Set timeline expectations

2. **If Option 2 Phase 1 Approved:**
   - Create implementation branch
   - Start with run cap (highest priority)
   - PR #1: Safety fixes (~50 lines)
   - PR #2: Metrics implementation (~400 lines)
   - PR #3: Documentation (~250 lines)

3. **Post-Phase 1:**
   - Gather metrics for 1 week
   - Evaluate: Does data justify Phase 2-4?
   - Plan Phase 2 if proceeding

---

**Plan Status:** ✅ READY FOR APPROVAL  
**Recommended:** Option 2 (Hybrid), start with Phase 1  
**Timeline:** 3 days for Phase 1 (critical), 3-4 weeks total if all phases approved  
**Next Action:** User decision on option and timeline
