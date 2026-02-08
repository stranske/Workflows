# Agents Auto-Pilot Design Compliance Evaluation

> **⚠️ SUPERSEDED (Feb 2026):** This document is outdated. Many gaps identified here
> (branch creation, optimizer race conditions, keepalive path divergence) have been
> fixed. See [`autopilot-40pr-evaluation-feb-2026.md`](./autopilot-40pr-evaluation-feb-2026.md)
> for the current evaluation.

**Created:** 2026-01-15  
**Purpose:** Evaluate whether `agents:auto-pilot` workflow operates according to its design specifications  
**Related Issue:** #880 (Metrics Collection)  
**Status:** EVALUATION COMPLETE

---

## Executive Summary

After re-evaluating the updated design documentation, **agents:auto-pilot now matches the intended inline-prep + workflow_run keepalive architecture**, but there is a **blocking integration gap** that prevents PR creation in practice.

### Critical Findings

1. **BRANCH CREATION GAP**: Auto-pilot assigns `agent:codex` but does not set `status:ready` or explicitly dispatch the belt dispatcher, so `codex/issue-*` branches never appear and PR creation stalls.
2. **KEEPALIVE PATH DIVERGENCE**: Auto-pilot directly dispatches keepalive instead of relying solely on Gate `workflow_run` (legacy workaround vs orchestrator-only contract).
3. **OBSERVABILITY GAP**: Auto-pilot itself does not emit structured step summaries; keepalive observability is covered elsewhere.

---

## Design vs Implementation Analysis

### Expected Design (from Documentation)

**From [`GoalsAndPlumbing.md`](../keepalive/GoalsAndPlumbing.md):**
- Keepalive is the core loop: "Issue labeled → Guarded check → Agent execution → Timed repeats"
- Auto-pilot should trigger keepalive, not replace it
- Agent routing via `agent:*` labels through keepalive workflow

**From [`SHORT_TERM_PLAN.md`](../plans/SHORT_TERM_PLAN.md):**
- Auto-pilot described as "end-to-end automation" with **inline** format/optimize/apply steps
- Should trigger: inline prep → agent assignment → PR creation → Gate `workflow_run` keepalive → verify

**From [`Observability_Contract.md`](../keepalive/Observability_Contract.md):**
- Mandatory one-line summaries: `DISPATCH:`, `INSTRUCTION:`, `WORKER:`, `SYNC:`
- PR-meta decides dispatch based on labels, Gate status, run cap
- Orchestrator posts instructions and coordinates worker/branch-sync

### Actual Implementation

**From [`.github/workflows/agents-auto-pilot.yml`](../../.github/workflows/agents-auto-pilot.yml):**

```yaml
# Line 5-6: "End-to-end automation: Issue → Format → Optimize → Apply → Agent → Keepalive → Merge"
# BUT: Format/Optimize/Apply run INLINE, not as separate workflows

# Lines 440-493: Execute step - Format (inline)
- name: Execute step - Format (inline)
  if: steps.next.outputs.next_step == 'format'
  run: |
    python scripts/langchain/issue_formatter.py ...
    gh issue edit "${ISSUE_NUMBER}" --body-file /tmp/formatted_body.md
    gh issue edit "${ISSUE_NUMBER}" --add-label "agents:formatted" || true

# Lines 495-561: Execute step - Optimize (inline)
- name: Execute step - Optimize (inline)
  if: steps.next.outputs.next_step == 'optimize'
  run: |
    python scripts/langchain/issue_optimizer.py ...
    gh issue comment "${ISSUE_NUMBER}" --body-file /tmp/comment.md
```

**Key Deviations:**

1. **Branch creation dependency**: Auto-pilot expects a `codex/issue-*` branch created by the belt dispatcher, but it never sets `status:ready` or triggers the dispatcher.
2. **Keepalive dispatch inconsistency**: Auto-pilot manually dispatches keepalive instead of waiting for Gate `workflow_run`.
3. **Auto-pilot observability**: No structured summary lines for auto-pilot steps (separate from keepalive contract).

---

## Architecture Gap Analysis

### Documented Architecture (Intended)

```
Issue with agents:auto-pilot label
   ↓
agents-auto-pilot.yml (inline prep + self re-dispatch)
   ├→ format issue inline → agents:formatted
   ├→ optimize issue inline → suggestions comment
   ├→ apply suggestions inline → agents:apply-suggestions
   ├→ add agent:codex → agent creates codex/issue-* branch
   └→ create PR + dispatch PR meta update
         ↓
Gate completes → agents-keepalive-loop (workflow_run)
         ↓
Codex runs → commits → Gate repeats until tasks complete
         ↓
Auto-pilot adds automerge + verify:evaluate
```

**Expected Observability Points:**
- Keepalive/PR-meta emit `DISPATCH:` / `INSTRUCTION:` / `WORKER:` / `SYNC:` lines.
- Auto-pilot posts step comments and uses cycle counts; structured summaries are optional.

### Actual Architecture (Implemented)

```
Issue with agents:auto-pilot label
    ↓
agents-auto-pilot.yml (single monolithic workflow)
    ↓
Step determination: format → optimize → apply → capability-check → create-pr → monitor-pr
    ↓
Each step runs INLINE (python scripts, gh CLI commands)
    ↓
After each step: self-dispatch with force_step parameter
    ↓
Eventually: adds agent:codex → capability check workflow runs
                           → creates PR with agents:keepalive label
                           → keepalive workflow takes over
    ↓
Monitors PR via linked_pr field, waits for keepalive completion
    ↓
When complete: check-completion → add automerge label
```

**Actual Observability:**
- Cycle count via comment search (`🤖 Auto-pilot step`)
- Progress comments per step
- NO structured metrics logging
- NO `DISPATCH:` / `INSTRUCTION:` / `WORKER:` summary lines

---

## Issue #880 Re-Evaluation

### Original Scope (from Issue #880)

```markdown
## Scope
Add auto-pilot specific metrics collection:
Create `scripts/autopilot_metrics_collector.py`
Update `agents-auto-pilot.yml` to emit metrics at each step
Track: step timing, cycle counts, failure reasons, escalations
```

### Problem: Scope Doesn't Match Implementation

1. **Step Timing**: Auto-pilot doesn't have discrete workflow steps to time
   - Format/optimize/apply are inline shell commands, not workflows
   - No clear start/end boundaries for metrics collection
   
2. **Cycle Counts**: Already tracked via comment search
   - Line 296-329: Counts comments with `🤖 Auto-pilot step`
   - Not a workflow metric—it's a comment string search
   
3. **Failure Reasons**: Not captured at workflow level
   - Inline steps fail via `exit 1` in shell scripts
   - No structured error classification like keepalive's `error_category`
   
4. **Escalations**: No formal escalation mechanism
   - Adds `needs-human` label after max cycles (line 300-325)
   - Not event-driven—just cycle limit enforcement

### What Metrics Are Actually Possible

Given the **monolithic inline architecture**, auto-pilot metrics would need to be:

1. **Per-Iteration Metrics** (similar to keepalive):
   ```json
   {
     "metric_type": "auto-pilot",
     "issue_number": 880,
     "cycle": 3,
     "timestamp": "2026-01-15T12:34:56Z",
     "step": "optimize",
     "duration_ms": 12500,
     "outcome": "success",
     "error": null
   }
   ```

2. **Workflow-Level Metrics**:
   - Total wall time from label add to done/failed
   - Number of self-dispatches
   - Which step took longest
   - Final outcome (merged, needs-human, failed)

3. **Integration Points** (existing workflow calls):
   - `agents-capability-check.yml` invocation (when agent:codex added)
   - `agents-keepalive-loop.yml` dispatch (after PR creation)
   - Verifier workflow dispatch (on issue close)

---

## Compliance Assessment

### Design Principles (from `Agents.md`)

| Principle | Compliant? | Evidence |
|-----------|-----------|----------|
| **Task Focus**: Agents work on PR tasks, not unrelated improvements | ✅ YES | Auto-pilot injects task appendix from formatted issue |
| **Agent Agnostic**: Routing via `agent:*` labels | ⚠️ PARTIAL | Hardcodes `agent:codex` (line 708), but keepalive routing works |
| **No `@codex` in Prompts**: Let routing handle agent selection | ✅ YES | Uses labels, not prompt mentions |
| **Verify Before Marking Complete**: Only check tasks after verification | ⚠️ UNCLEAR | Delegates to keepalive, auto-pilot doesn't mark tasks |

### Keepalive Contract (from `GoalsAndPlumbing.md`)

| Requirement | Compliant? | Evidence |
|-------------|-----------|----------|
| **Activation Guardrails**: PR opt-in, Gate green, Tasks present | ❌ NO | Auto-pilot bypasses Gate requirement for issue prep |
| **Repeat Contract**: Re-validate guardrails before next run | ❌ NO | Self-dispatch doesn't check Gate or run cap |
| **Run Cap Enforcement**: Max 1 concurrent, respect override labels | ❌ NO | No run cap enforcement in auto-pilot |
| **Pause & Stop Controls**: Respect `agents:paused`, `needs-human` | ⚠️ PARTIAL | Checks `needs-human` (line 232), not `agents:paused` |
| **No-Noise Policy**: No comments when preconditions missing | ❌ NO | Posts "Auto-pilot step X" on every cycle |
| **Instruction Prompt Contract**: Task injection via appendix | N/A | Delegates to keepalive for PR work |

### Observability Contract (from `Observability_Contract.md`)

| Requirement | Compliant? | Evidence |
|-------------|-----------|----------|
| **Mandatory One-Line Summaries**: `DISPATCH:`, `INSTRUCTION:`, `WORKER:`, `SYNC:` | ❌ NO | No structured summaries |
| **Reaction Lock**: Prevent duplicate dispatch via 🚀 reaction | ❌ NO | Uses concurrency group, not reactions |
| **Run-Cap Definition**: Count active runs, respect cap | ❌ NO | No run cap logic |
| **Failure Reasons**: Canonical list of skip/fail reasons | ⚠️ PARTIAL | Has `needs-human` but no structured reasons |

---

## Root Cause Analysis

### Why Implementation Diverged from Design

**From [`AUTOPILOT_FIX_HISTORY.md`](../plans/AUTOPILOT_FIX_HISTORY.md):**

- 32 PRs since 2026-01-10 (5 days of rapid iteration)
- Key issues fixed:
  - Race conditions between auto-pilot and intake/auto-label workflows
  - Step ordering (optimizer before agent)
  - Re-dispatch failures (pipeline not continuing)
  - Label interference (other workflows triggering when auto-pilot active)

**Engineering Trade-offs Made:**

1. **Inline Execution** (PR #776, #819):
   - **Reason**: "Running optimizer inline (not via label trigger)" to avoid race conditions
   - **Trade-off**: Lost observability, violated separation of concerns
   - **Comment in code** (line 438): "NOTE: Run optimizer inline, not via label"

2. **Self-Dispatch Loop** (PR #765, #767):
   - **Reason**: GITHUB_TOKEN labels don't trigger workflows
   - **Trade-off**: Created polling loop instead of event-driven architecture
   - **Implementation** (line 1039): `workflow_dispatch` with `force_step` parameter

3. **Label Bypass** (PR #834, #835):
   - **Reason**: Skip intake when auto-pilot active to prevent interference
   - **Trade-off**: Parallel automation tracks instead of unified system

**Architectural Debt:**
- Started as orchestrator (dispatch other workflows)
- Evolved into monolith (run everything inline)
- Never refactored back to intended design

---

## Impact on Issue #880

### Why Metrics Proposal Doesn't Fit

Issue #880 was written assuming auto-pilot follows the keepalive/orchestrator pattern:
- Separate workflow steps with discrete start/end
- `DISPATCH:` summaries for each step transition
- Structured error classification

**Actual auto-pilot:**
- Single workflow with inline shell scripts
- No clear step boundaries for timing
- Exit codes, not error categories

### What Would Need to Change

**Option A: Make Auto-Pilot Match Design** (HIGH EFFORT)

1. Refactor inline steps back to separate workflows:
   - `agents-issue-formatter.yml` (already exists, not used)
   - `agents-issue-optimizer.yml` (already exists, not used)
   - `agents-apply-suggestions.yml` (already exists, not used)

2. Implement observability contract:
   - Add `DISPATCH:` / `INSTRUCTION:` / `WORKER:` summaries
   - Add run cap enforcement
   - Add reaction locks

3. Then implement metrics as designed in #880

**Option B: Adapt Metrics to Current Implementation** (LOW EFFORT)

1. Create `scripts/autopilot_metrics_emitter.py`:
   - Takes step name, start time, end time, outcome
   - Writes NDJSON to artifact or comment

2. Wrap each step in timing capture:
   ```yaml
   - name: Emit start metric
     run: |
       echo "$(date -u +%s)" > /tmp/step_start
   
   - name: Execute step - Format (inline)
     # ... existing code ...
   
   - name: Emit end metric  
     run: |
       start=$(cat /tmp/step_start)
       end=$(date -u +%s)
       python scripts/autopilot_metrics_emitter.py \
         --step format --start $start --end $end --outcome success
   ```

3. Update #880 scope to match current architecture

---

## Deviations Summary

### CRITICAL Deviations (Break Design Contract)

1. **Inline Execution**: Format/optimize/apply run as shell scripts, not separate workflows
   - **Impact**: No workflow-level observability, metrics, or reusability
   - **Location**: Lines 440-660 in `agents-auto-pilot.yml`

2. **Missing Observability**: No `DISPATCH:` / `INSTRUCTION:` / `WORKER:` summaries
   - **Impact**: Can't trace decisions, failures hidden in logs
   - **Location**: Entire workflow lacks structured logging

3. **No Run Cap**: Can spam infinite self-dispatches
   - **Impact**: Could DOS Actions quota, no throttling
   - **Location**: Re-dispatch step (line 1039) has no cap check

4. **Bypasses Gate**: Issue prep runs without Gate success
   - **Impact**: Breaks safety contract, could process malicious issues
   - **Location**: Steps run on label add, not Gate pass

### MAJOR Deviations (Violate Documented Behavior)

5. **Self-Dispatch Loop**: Uses `workflow_dispatch` instead of event triggers
   - **Impact**: Polling instead of reactive, delays and wasted runs
   - **Location**: Lines 1039-1096

6. **Label Misuse**: Adds labels but tells them not to trigger workflows
   - **Impact**: Confusing, labels don't mean what they say
   - **Location**: Lines 436, 544, 659 ("don't trigger workflow")

7. **Parallel Track**: Creates separate automation path from keepalive
   - **Impact**: Two systems to maintain, duplicate logic
   - **Location**: Entire workflow is parallel to keepalive

### MINOR Deviations (Implementation Details)

8. **Hardcoded Agent**: Uses `agent:codex` directly instead of variable
   - **Impact**: Not extensible to other agents
   - **Location**: Line 708

9. **Comment-Based State**: Tracks cycles via comment string search
   - **Impact**: Fragile, can break if comment format changes
   - **Location**: Lines 296-329

10. **No Pause Label**: Doesn't check `agents:paused` or `agents:auto-pilot-pause`
    - **Impact**: Can't pause without removing label entirely
    - **Location**: Lines 229-245 (checks `needs-human` but not pause labels)

---

## Recommendations

### Immediate Actions (Low Effort, High Value)

1. **Update Documentation** to match implementation:
   - Revise `SHORT_TERM_PLAN.md` to describe monolithic architecture
   - Add "Auto-Pilot Architecture" section to `docs/keepalive/`
   - Document that auto-pilot is NOT keepalive-based

2. **Revise Issue #880** to match current architecture:
   - Replace "step timing" with "cycle timing"
   - Replace "workflow metrics" with "inline step metrics"
   - See "Option B" implementation above

3. **Add Run Cap** to prevent infinite loops:
   ```yaml
   - name: Check dispatch count
     run: |
       count=$(gh api "/repos/${{ github.repository }}/actions/workflows/agents-auto-pilot.yml/runs" \
         --jq '[.workflow_runs[] | select(.status == "queued" or .status == "in_progress")] | length')
       if [ "$count" -ge 3 ]; then
         echo "Too many concurrent auto-pilot runs ($count)"
         exit 1
       fi
   ```

### Long-Term Refactoring (High Effort, Architectural Fix)

4. **Separate Workflows** (aligns with original design):
   - Use existing `agents-issue-formatter.yml`, `agents-issue-optimizer.yml`
   - Auto-pilot becomes pure orchestrator (dispatches, waits, checks status)
   - Each workflow gets its own observability

5. **Implement Observability Contract**:
   - Add `DISPATCH:` summaries to auto-pilot
   - Add metrics schema for auto-pilot (extend keepalive schema)
   - Unified metrics collection across all agent workflows

6. **Unify with Keepalive**:
   - Make auto-pilot a "prep phase" that adds `agent:codex` when ready
   - Let keepalive handle all PR work (it already does)
   - Reduce auto-pilot to: format → optimize → apply → label
   - Remove PR monitoring from auto-pilot (keepalive already does this)

---

## Conclusion

**agents:auto-pilot does NOT work as designed.** It evolved into a monolithic inline workflow through rapid iteration to fix race conditions and label interference. While functional, it:

- Violates separation of concerns (runs formatters inline)
- Bypasses observability contract (no structured summaries)
- Creates parallel track to keepalive (two systems)
- Makes issue #880 metrics impossible as specified

**For Issue #880:**
- Current scope is NOT ACHIEVABLE without major refactoring
- Recommend revising scope to match inline architecture (Option B)
- Alternative: Do full refactoring first (Option A), then implement metrics

**Next Steps:**
1. Decide: Quick fix (#880 scope change) or refactor (align to design)?
2. If quick fix: Implement Option B metrics
3. If refactor: Follow Long-Term Refactoring plan
4. Either way: Update documentation to match reality

---

**Evaluation Status:** COMPLETE  
**Documentation Read:** ✅ All keepalive docs, SHORT_TERM_PLAN, AUTOPILOT_FIX_HISTORY  
**Code Reviewed:** ✅ agents-auto-pilot.yml (1140 lines), agents-keepalive-loop.yml (452 lines)  
**Recommendation:** Issue #880 needs scope revision to match current architecture
