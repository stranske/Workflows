# Auto-Pilot Design Deviations - Summary Report

**Created:** 2026-01-15  
**Related:** [Full Evaluation](./autopilot-design-compliance-evaluation.md), [Issue #880 Revision](./issue-880-revised-scope.md)  
**Status:** COMPLETE

---

## Quick Summary

**agents:auto-pilot does NOT work as designed.** It evolved from an orchestrator into a monolithic inline workflow through 32 PRs over 5 days (2026-01-10 to 2026-01-15).

### Key Deviations

| Category | Deviation | Severity | Impact |
|----------|-----------|----------|--------|
| **Architecture** | Runs format/optimize/apply inline, not as separate workflows | ❌ CRITICAL | No workflow-level observability, breaks reusability |
| **Observability** | No `DISPATCH:` / `INSTRUCTION:` / `WORKER:` summaries | ❌ CRITICAL | Can't trace decisions, failures hidden |
| **Safety** | No run cap enforcement | ❌ CRITICAL | Can spam infinite dispatches |
| **Compliance** | Bypasses Gate requirement for issue prep | ❌ CRITICAL | Breaks safety contract |
| **Design Pattern** | Self-dispatch loop instead of event triggers | ⚠️ MAJOR | Polling vs reactive |
| **Labels** | Adds labels but blocks their workflow triggers | ⚠️ MAJOR | Confusing semantics |
| **Separation** | Parallel track to keepalive, not integrated | ⚠️ MAJOR | Two systems to maintain |
| **Extensibility** | Hardcodes `agent:codex` | ⚠️ MINOR | Not multi-agent ready |

---

## Root Cause

**Engineering trade-offs during rapid iteration:**

1. **Race Conditions** (PR #819, #834): Other workflows triggered by labels → inline execution to bypass
2. **Label Triggers Don't Work** (PR #765, #767): GITHUB_TOKEN labels don't trigger workflows → self-dispatch loop
3. **Step Ordering** (PR #776, #794): Need optimizer before agent → inline to guarantee order

**Result:** Monolithic workflow that violates original design but solves immediate problems.

---

## Impact on Issue #880

**Original scope is NOT achievable** without major refactoring.

Issue #880 asks for:
- "Step-by-step timing" (no discrete workflow steps)
- "Update agents-auto-pilot.yml to emit metrics at each step" (steps are inline shell scripts)
- "Failure reasons" (uses exit codes, not error categories)

**Recommended Action:** Revise #880 scope to match inline architecture  
**Alternative:** Refactor auto-pilot first (1-2 weeks), then implement metrics as designed

See [Issue #880 Revised Scope](./issue-880-revised-scope.md) for proposed solution.

---

## 10 Specific Deviations

### CRITICAL (Violate Safety/Design Contract)

#### 1. Inline Execution of Formatters/Optimizers
**Location:** [agents-auto-pilot.yml](../../.github/workflows/agents-auto-pilot.yml) lines 440-660

**Documented Behavior:**
- Auto-pilot should dispatch `agents-issue-formatter.yml`, `agents-issue-optimizer.yml`
- Each workflow has own observability and metrics

**Actual Behavior:**
```yaml
# Line 440: Execute step - Format (inline)
run: |
  python scripts/langchain/issue_formatter.py ...
  gh issue edit "${ISSUE_NUMBER}" --body-file /tmp/formatted_body.md
  gh issue edit "${ISSUE_NUMBER}" --add-label "agents:formatted" || true
```

**Impact:** No workflow-level observability, can't reuse formatters independently

---

#### 2. Missing Observability Contract
**Location:** Entire workflow

**Documented Behavior:** (from [`Observability_Contract.md`](../keepalive/Observability_Contract.md))
```
DISPATCH: ok=<true|false> path=<comment|gate> reason=<ok|...> pr=#<PR> ...
INSTRUCTION: ok=<true|false> author=<stranske> comment=<ID> ...
WORKER: action=<execute|skip> reason=<new-instruction|...> ...
```

**Actual Behavior:** No structured summaries, only prose comments and cycle counts

**Impact:** Can't trace why workflow made decisions, failures hidden in logs

---

#### 3. No Run Cap Enforcement
**Location:** Re-dispatch step (line 1039)

**Documented Behavior:** (from [`GoalsAndPlumbing.md`](../keepalive/GoalsAndPlumbing.md))
- "Default limit: Maximum of 1 concurrent agent run per PR"
- "Label override: Respect `agents:max-parallel:<K>` when present"

**Actual Behavior:**
```yaml
# No cap check before re-dispatch
await github.rest.actions.createWorkflowDispatch({
  workflow_id: 'agents-auto-pilot.yml',
  ref: 'main',
  inputs: { issue_number: issueNumber.toString(), force_step: nextStep }
});
```

**Impact:** Can spawn unlimited concurrent runs, DOS Actions quota

---

#### 4. Bypasses Gate Requirement
**Location:** Trigger conditions (lines 60-67)

**Documented Behavior:** (from [`GoalsAndPlumbing.md`](../keepalive/GoalsAndPlumbing.md))
- "Gate green: The Gate workflow for the current head SHA completed successfully"
- "Keepalive must not dispatch an agent unless all conditions hold"

**Actual Behavior:**
```yaml
if: |
  github.event_name == 'workflow_dispatch' ||
  (github.event.action == 'labeled' && (
    github.event.label.name == 'agents:auto-pilot' ||
    github.event.label.name == 'agent:codex'
  ))
```
No Gate check for issue prep steps (format, optimize, apply)

**Impact:** Can process malicious issues without CI validation

---

### MAJOR (Violate Documented Behavior)

#### 5. Self-Dispatch Loop
**Location:** Lines 1039-1096

**Documented Behavior:**
- Workflows trigger on labels, PR events
- Event-driven architecture

**Actual Behavior:**
```yaml
await github.rest.actions.createWorkflowDispatch({
  workflow_id: 'agents-auto-pilot.yml',
  ref: 'main',
  inputs: { issue_number: issueNumber.toString(), force_step: nextStep }
});
```
Polls by repeatedly dispatching itself with `force_step` parameter

**Impact:** Not reactive, delays between steps, wasted workflow runs

---

#### 6. Label Misuse
**Location:** Lines 436, 544, 659

**Documented Behavior:**
- Labels trigger workflows
- `agents:formatted` should trigger downstream workflows

**Actual Behavior:**
```yaml
# Add marker label (but don't trigger workflow)
gh issue edit "${ISSUE_NUMBER}" --add-label "agents:formatted" || true
```
Inline comment: "don't trigger workflow"

**Impact:** Labels don't mean what they say, confusing for operators

---

#### 7. Parallel Track to Keepalive
**Location:** Entire workflow design

**Documented Behavior:** (from [`SHORT_TERM_PLAN.md`](../plans/SHORT_TERM_PLAN.md))
- Auto-pilot orchestrates existing workflows
- Keepalive handles PR work
- Unified system

**Actual Behavior:**
- Auto-pilot does issue prep inline (format, optimize, apply)
- Eventually hands off to keepalive for PR work
- Two separate automation tracks

**Impact:** Duplicate logic, two systems to maintain

---

### MINOR (Implementation Details)

#### 8. Hardcoded Agent Type
**Location:** Line 708

**Documented Behavior:** (from [`MULTI_AGENT_ROUTING.md`](../keepalive/MULTI_AGENT_ROUTING.md))
- Agent routing via `agent:*` labels
- Extensible to multiple agents

**Actual Behavior:**
```yaml
labels: ['agent:codex', 'agents:keepalive', 'autofix']
```
Hardcodes `agent:codex` instead of using variable

**Impact:** Not ready for multi-agent support (Claude, Gemini)

---

#### 9. Comment-Based State
**Location:** Lines 296-329

**Documented Behavior:**
- State tracked in workflow outputs, labels, issue fields

**Actual Behavior:**
```javascript
const stepComments = allComments.filter(c =>
  typeof c.body === 'string' && c.body.includes('🤖 Auto-pilot step')
);
const stepCount = stepComments.length;
```

**Impact:** Fragile, breaks if comment format changes

---

#### 10. Missing Pause Label Check
**Location:** Lines 229-245

**Documented Behavior:** (from [`GoalsAndPlumbing.md`](../keepalive/GoalsAndPlumbing.md))
- "Removing the `agent:*` label halts new dispatches"
- "Respect the `agents:paused` label"

**Actual Behavior:**
```javascript
if (labels.includes('agents:auto-pilot-pause')) {
  core.info('Auto-pilot paused by agents:auto-pilot-pause label');
  ...
}
```
Checks custom pause label, NOT documented `agents:paused`

**Impact:** Inconsistent label semantics across workflows

---

## Compliance Matrix

| Design Requirement | Source Document | Compliant? | Evidence |
|-------------------|----------------|-----------|----------|
| **Activation Guardrails** | GoalsAndPlumbing.md §1 | ❌ NO | Bypasses Gate for issue prep |
| **Repeat Contract** | GoalsAndPlumbing.md §2 | ❌ NO | Self-dispatch without guardrails |
| **Run Cap Enforcement** | GoalsAndPlumbing.md §3 | ❌ NO | No cap check before dispatch |
| **Pause Controls** | GoalsAndPlumbing.md §4 | ⚠️ PARTIAL | Checks `needs-human`, not `agents:paused` |
| **No-Noise Policy** | GoalsAndPlumbing.md §5 | ❌ NO | Posts "Auto-pilot step X" on every cycle |
| **Task Injection** | GoalsAndPlumbing.md §6 | N/A | Delegates to keepalive |
| **Agent Routing** | MULTI_AGENT_ROUTING.md | ⚠️ PARTIAL | Hardcodes `agent:codex` |
| **Observability** | Observability_Contract.md | ❌ NO | No structured summaries |
| **Task Focus** | Agents.md | ✅ YES | Injects task appendix |
| **Agent Agnostic** | Agents.md | ⚠️ PARTIAL | Keepalive routing works |

**Overall Compliance:** 1/10 fully compliant, 4/10 partial, 5/10 non-compliant

---

## Why This Matters

### Immediate Risks

1. **No Throttling:** Can spawn unlimited runs, exhaust Actions minutes
2. **Hidden Failures:** No structured logs = debugging requires reading raw output
3. **Fragile State:** Comment string matching can break

### Long-Term Debt

1. **Maintenance Burden:** Two automation systems (auto-pilot + keepalive) with duplicate logic
2. **Feature Velocity:** Can't add new agents/steps without inline code changes
3. **Testing:** Inline steps hard to unit test, no workflow-level tests

### Metrics Impact

- Can't implement issue #880 as designed (no discrete steps to time)
- Would need major refactoring (1-2 weeks) to match original spec
- Quick fix: Revise scope to match inline architecture

---

## Recommendations by Priority

### Immediate (This Week)

1. ✅ **Update Documentation** to match implementation
   - Add "Auto-Pilot Architecture" doc explaining monolithic design
   - Mark design docs as "aspirational" vs "actual"

2. ✅ **Revise Issue #880** scope
   - Use proposed [revised scope](./issue-880-revised-scope.md)
   - Emit metrics for inline steps, not workflow boundaries

3. ⚠️ **Add Run Cap** to prevent infinite loops
   ```yaml
   - name: Check concurrent runs
     run: |
       count=$(gh api "/repos/${{ github.repository }}/actions/workflows/agents-auto-pilot.yml/runs" \
         --jq '[.workflow_runs[] | select(.status == "queued" or .status == "in_progress")] | length')
       if [ "$count" -ge 3 ]; then exit 1; fi
   ```

### Short-Term (Next Sprint)

4. **Implement Metrics** per revised #880 scope
   - Wrap inline steps with timing
   - Emit NDJSON to logs
   - Document schema

5. **Add Pause Label** support
   - Check `agents:paused` in addition to `needs-human`
   - Consistent with keepalive

### Long-Term (Next Quarter)

6. **Refactor to Match Design** (if desired)
   - Separate workflows for format/optimize/apply
   - Implement observability contract
   - Unify with keepalive architecture

7. **Multi-Agent Support**
   - Parameterize agent type
   - Support `agent:claude`, `agent:gemini`
   - Agent-agnostic step logic

---

## Decision Matrix

### Quick Fix vs Refactor

| Approach | Effort | Risk | Benefits | When to Choose |
|----------|--------|------|----------|----------------|
| **Quick Fix** | 1-2 days | Low | Metrics working this week | Need observability now, refactor later |
| **Document Reality** | 4 hours | None | Clear expectations | Accept current design as-is |
| **Full Refactor** | 1-2 weeks | High | Matches design, better architecture | Have time, want proper separation |

**Recommendation:** Quick Fix + Document Reality

---

## Next Steps

### For User
1. Decide: Quick fix (#880 scope change) or full refactor (align to design)?
2. Approve revised scope or request changes
3. Prioritize run cap fix (high risk if ignored)

### For Implementation
1. If quick fix: Implement [revised #880](./issue-880-revised-scope.md)
2. If refactor: Create separate planning issue
3. Either way: Update docs to match reality

---

**Evaluation Complete:** ✅  
**Files Created:**
- [autopilot-design-compliance-evaluation.md](./autopilot-design-compliance-evaluation.md) - Full analysis
- [issue-880-revised-scope.md](./issue-880-revised-scope.md) - Proposed solution
- [autopilot-deviations-summary.md](./autopilot-deviations-summary.md) - This document

**Ready for:** User decision on path forward
