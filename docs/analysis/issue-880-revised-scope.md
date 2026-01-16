# Issue #880 Revised Scope - Auto-Pilot Metrics Collection

**Created:** 2026-01-15  
**Based On:** [Auto-Pilot Design Compliance Evaluation](./autopilot-design-compliance-evaluation.md)  
**Original Issue:** #880  
**Status:** PROPOSED REVISION

---

## Why This Revision Is Needed

The original scope for issue #880 assumed auto-pilot follows a multi-workflow orchestration pattern with discrete steps. After reading design docs and analyzing implementation:

- Auto-pilot runs format/optimize/apply **inline** (shell scripts in one workflow)
- No separate workflow boundaries to time
- No `DISPATCH:` summaries or structured observability
- Cycles tracked via comment string search, not metrics

**Original scope is not achievable without major refactoring.**

See [full evaluation](./autopilot-design-compliance-evaluation.md) for detailed analysis.

---

## Revised Scope

### What Auto-Pilot Actually Needs

**Observability for the monolithic inline workflow:**

1. **Cycle-Level Metrics** (per self-dispatch iteration):
   - Which step executed (format, optimize, apply, capability-check, monitor-pr, etc.)
   - How long it took (wall time)
   - Outcome (success, failure, skipped)
   - Error details if failed

2. **Issue-Level Summary** (end-to-end):
   - Total cycles required
   - Total wall time from label add to completion
   - Final outcome (merged, needs-human, failed, paused)
   - Which step took longest

3. **Integration Tracking** (workflow boundaries that exist):
   - When `agents-capability-check.yml` was triggered
   - When `agents-keepalive-loop.yml` was dispatched
   - When PR was created
   - When verification was triggered

### What's Out of Scope

- ❌ Step-by-step timing of separate workflows (they don't exist)
- ❌ `DISPATCH:` summaries (not part of auto-pilot architecture)
- ❌ Real-time dashboards (batch collection only)
- ❌ LangSmith integration (separate issue #807)

---

## Implementation Approach

### Option A: Lightweight Metrics (RECOMMENDED)

Add metrics emission at key points in `agents-auto-pilot.yml`:

#### 1. Cycle Start Metric

```yaml
- name: Emit cycle start metric
  if: steps.context.outputs.should_continue == 'true'
  env:
    ISSUE_NUMBER: ${{ steps.context.outputs.issue_number }}
    STEP_COUNT: ${{ steps.cycles.outputs.count }}
    NEXT_STEP: ${{ steps.next.outputs.next_step }}
  run: |
    python scripts/autopilot_metrics.py emit-cycle-start \
      --issue "$ISSUE_NUMBER" \
      --cycle "$((STEP_COUNT + 1))" \
      --step "$NEXT_STEP"
```

#### 2. Step Execution Metrics

Wrap each step with timing:

```yaml
- name: Execute step - Format (inline)
  if: steps.next.outputs.next_step == 'format'
  env:
    ISSUE_NUMBER: ${{ steps.context.outputs.issue_number }}
    STEP_COUNT: ${{ steps.cycles.outputs.count }}
  run: |
    # Capture start time
    start_ts=$(date -u +%s)
    
    # Post progress comment
    gh issue comment "${ISSUE_NUMBER}" --body "..."
    
    # Format the issue
    if python scripts/langchain/issue_formatter.py ...; then
      outcome="success"
      error=""
    else
      outcome="failure"
      error="Formatter script failed"
    fi
    
    # Capture end time and emit metric
    end_ts=$(date -u +%s)
    duration=$((end_ts - start_ts))
    
    python scripts/autopilot_metrics.py emit-step \
      --issue "$ISSUE_NUMBER" \
      --cycle "$((STEP_COUNT + 1))" \
      --step "format" \
      --duration "$duration" \
      --outcome "$outcome" \
      --error "$error"
    
    # Exit with appropriate code
    if [ "$outcome" = "failure" ]; then exit 1; fi
```

#### 3. Cycle End Metric

```yaml
- name: Emit cycle end metric
  if: always()
  env:
    ISSUE_NUMBER: ${{ steps.context.outputs.issue_number }}
    STEP_COUNT: ${{ steps.cycles.outputs.count }}
    NEXT_STEP: ${{ steps.next.outputs.next_step }}
  run: |
    python scripts/autopilot_metrics.py emit-cycle-end \
      --issue "$ISSUE_NUMBER" \
      --cycle "$((STEP_COUNT + 1))" \
      --next-action "$NEXT_STEP"
```

#### 4. Issue Summary Metric (when complete)

```yaml
- name: Emit issue summary metric
  if: steps.next.outputs.next_step == 'done'
  env:
    ISSUE_NUMBER: ${{ steps.context.outputs.issue_number }}
    STEP_COUNT: ${{ steps.cycles.outputs.count }}
  run: |
    python scripts/autopilot_metrics.py emit-summary \
      --issue "$ISSUE_NUMBER" \
      --total-cycles "$STEP_COUNT" \
      --outcome "completed"
```

### Option B: Metrics Collector Script

Create `scripts/autopilot_metrics.py` with these commands:

```python
#!/usr/bin/env python3
"""Auto-pilot metrics collection script."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

def emit_cycle_start(issue: int, cycle: int, step: str):
    """Emit metric when auto-pilot cycle starts."""
    metric = {
        "metric_type": "auto-pilot-cycle-start",
        "issue_number": issue,
        "cycle": cycle,
        "step": step,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    print(json.dumps(metric), flush=True)

def emit_step(issue: int, cycle: int, step: str, duration: int, outcome: str, error: str):
    """Emit metric for a completed step."""
    metric = {
        "metric_type": "auto-pilot-step",
        "issue_number": issue,
        "cycle": cycle,
        "step": step,
        "duration_ms": duration * 1000,  # Convert seconds to ms
        "outcome": outcome,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    if error:
        metric["error"] = error
    print(json.dumps(metric), flush=True)

def emit_cycle_end(issue: int, cycle: int, next_action: str):
    """Emit metric when auto-pilot cycle ends."""
    metric = {
        "metric_type": "auto-pilot-cycle-end",
        "issue_number": issue,
        "cycle": cycle,
        "next_action": next_action,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    print(json.dumps(metric), flush=True)

def emit_summary(issue: int, total_cycles: int, outcome: str):
    """Emit summary metric for entire auto-pilot run."""
    metric = {
        "metric_type": "auto-pilot-summary",
        "issue_number": issue,
        "total_cycles": total_cycles,
        "outcome": outcome,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    print(json.dumps(metric), flush=True)

def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest='command', required=True)
    
    # emit-cycle-start
    p = subparsers.add_parser('emit-cycle-start')
    p.add_argument('--issue', type=int, required=True)
    p.add_argument('--cycle', type=int, required=True)
    p.add_argument('--step', required=True)
    
    # emit-step
    p = subparsers.add_parser('emit-step')
    p.add_argument('--issue', type=int, required=True)
    p.add_argument('--cycle', type=int, required=True)
    p.add_argument('--step', required=True)
    p.add_argument('--duration', type=int, required=True)
    p.add_argument('--outcome', required=True)
    p.add_argument('--error', default='')
    
    # emit-cycle-end
    p = subparsers.add_parser('emit-cycle-end')
    p.add_argument('--issue', type=int, required=True)
    p.add_argument('--cycle', type=int, required=True)
    p.add_argument('--next-action', required=True)
    
    # emit-summary
    p = subparsers.add_parser('emit-summary')
    p.add_argument('--issue', type=int, required=True)
    p.add_argument('--total-cycles', type=int, required=True)
    p.add_argument('--outcome', required=True)
    
    args = parser.parse_args()
    
    if args.command == 'emit-cycle-start':
        emit_cycle_start(args.issue, args.cycle, args.step)
    elif args.command == 'emit-step':
        emit_step(args.issue, args.cycle, args.step, args.duration, args.outcome, args.error)
    elif args.command == 'emit-cycle-end':
        emit_cycle_end(args.issue, args.cycle, args.next_action)
    elif args.command == 'emit-summary':
        emit_summary(args.issue, args.total_cycles, args.outcome)

if __name__ == '__main__':
    main()
```

### Metrics Schema

```typescript
// Cycle start
interface AutoPilotCycleStart {
  metric_type: "auto-pilot-cycle-start";
  issue_number: number;
  cycle: number;
  step: string;  // "format" | "optimize" | "apply" | "capability-check" | "create-pr" | "monitor-pr" | "check-completion"
  timestamp: string;  // ISO 8601 UTC
}

// Step completion
interface AutoPilotStep {
  metric_type: "auto-pilot-step";
  issue_number: number;
  cycle: number;
  step: string;
  duration_ms: number;
  outcome: "success" | "failure" | "skipped";
  error?: string;
  timestamp: string;
}

// Cycle end
interface AutoPilotCycleEnd {
  metric_type: "auto-pilot-cycle-end";
  issue_number: number;
  cycle: number;
  next_action: string;  // What will happen next: "done" | "format" | "optimize" | etc.
  timestamp: string;
}

// Summary (when auto-pilot completes or fails)
interface AutoPilotSummary {
  metric_type: "auto-pilot-summary";
  issue_number: number;
  total_cycles: number;
  outcome: "completed" | "needs-human" | "failed" | "paused";
  timestamp: string;
}
```

### Example Metrics Output

```json
{"metric_type":"auto-pilot-cycle-start","issue_number":880,"cycle":1,"step":"format","timestamp":"2026-01-15T12:00:00Z"}
{"metric_type":"auto-pilot-step","issue_number":880,"cycle":1,"step":"format","duration_ms":12500,"outcome":"success","timestamp":"2026-01-15T12:00:12Z"}
{"metric_type":"auto-pilot-cycle-end","issue_number":880,"cycle":1,"next_action":"optimize","timestamp":"2026-01-15T12:00:13Z"}

{"metric_type":"auto-pilot-cycle-start","issue_number":880,"cycle":2,"step":"optimize","timestamp":"2026-01-15T12:02:00Z"}
{"metric_type":"auto-pilot-step","issue_number":880,"cycle":2,"step":"optimize","duration_ms":8400,"outcome":"success","timestamp":"2026-01-15T12:02:08Z"}
{"metric_type":"auto-pilot-cycle-end","issue_number":880,"cycle":2,"next_action":"apply","timestamp":"2026-01-15T12:02:09Z"}

...

{"metric_type":"auto-pilot-summary","issue_number":880,"total_cycles":8,"outcome":"completed","timestamp":"2026-01-15T12:45:00Z"}
```

---

## Comparison to Keepalive Metrics

**Keepalive metrics** ([`METRICS_SCHEMA.md`](../keepalive/METRICS_SCHEMA.md)):
```json
{"pr_number":1234,"iteration":2,"timestamp":"...","action":"retry","error_category":"none","duration_ms":4821,"tasks_total":14,"tasks_complete":6}
```

**Auto-pilot metrics** (this proposal):
```json
{"metric_type":"auto-pilot-step","issue_number":880,"cycle":2,"step":"optimize","duration_ms":8400,"outcome":"success","timestamp":"..."}
```

**Key Differences:**
- Keepalive: PR-focused, tracks task progress
- Auto-pilot: Issue-focused, tracks pipeline progress
- Keepalive: `action` (run, stop, retry)
- Auto-pilot: `step` (format, optimize, apply, etc.)
- Keepalive: `error_category`
- Auto-pilot: `outcome` + optional `error` string

---

## Revised Tasks for Issue #880

### Updated Issue Body

```markdown
## Why

Auto-pilot workflow performance is not currently tracked. We need to capture cycle timing, step outcomes, and failure modes to identify bottlenecks and improve the end-to-end automation.

## Scope

Add auto-pilot specific metrics collection:
- Create `scripts/autopilot_metrics.py` CLI tool
- Update `agents-auto-pilot.yml` to emit metrics at cycle boundaries
- Track: step timing, cycle counts, outcomes, errors
- Store metrics in workflow logs (NDJSON format)

## Non-Goals

- Modifying auto-pilot core behavior (metrics only)
- Real-time dashboards (batch collection via logs)
- LangSmith integration (separate issue #807)
- Refactoring auto-pilot to match original design (separate effort)

## Tasks

- [ ] Create `scripts/autopilot_metrics.py` with emit commands
- [ ] Add cycle-start metric emission
- [ ] Wrap each step (format, optimize, apply) with timing
- [ ] Add cycle-end metric emission
- [ ] Add summary metric on completion/failure
- [ ] Write unit tests for metrics script
- [ ] Document metrics schema in `docs/metrics/`
- [ ] Add metrics interpretation guide

## Acceptance Criteria

- [ ] `scripts/autopilot_metrics.py` exists and passes tests
- [ ] Auto-pilot workflow emits cycle/step/summary metrics
- [ ] Metrics are NDJSON, parseable by standard tools
- [ ] Documentation explains schema and interpretation
- [ ] No changes to auto-pilot behavior (observability only)
```

### Implementation Notes

- **Metric Storage**: Workflow logs (stdout), parseable with `jq`
- **Aggregation**: Post-hoc analysis via `gh run view` + `jq` filters
- **Schema**: Documented in `docs/metrics/autopilot-metrics-schema.md`
- **Testing**: Unit tests for `autopilot_metrics.py` CLI commands

---

## Migration Path

### Phase 1: Add Metrics (Low Risk)

1. Create `scripts/autopilot_metrics.py`
2. Add metric emission at 3-5 key points:
   - Cycle start (after "Determine next step")
   - Step completion (after each inline step)
   - Cycle end (before re-dispatch)
   - Summary (in "done" and "exceeded" paths)
3. Write docs and tests
4. Deploy, verify logs

**Estimated Effort:** 1-2 days  
**Risk:** Very low (only adds logging)

### Phase 2: Analysis Tools (Optional)

1. Create `scripts/analyze_autopilot_metrics.py`:
   - Parse NDJSON from workflow logs
   - Aggregate by issue, step, outcome
   - Output summary tables

2. Add to CI:
   - Periodic job to analyze metrics
   - Post summary to issues

**Estimated Effort:** 1 day  
**Risk:** Low

### Phase 3: Refactoring (Future)

If we want auto-pilot to match its original design:
1. Separate inline steps back to workflows
2. Implement orchestrator pattern
3. Add `DISPATCH:` summaries
4. Unify with keepalive observability

**Estimated Effort:** 1-2 weeks  
**Risk:** High (major refactoring)  
**Benefit:** Proper separation of concerns, reusable workflows

---

## Recommendation

✅ **Implement Phase 1** (add metrics to current architecture)

This gives us:
- Visibility into auto-pilot performance
- Data to inform future refactoring
- Low risk, high value
- Aligns scope with reality

Then decide on Phase 2 (analysis tools) or Phase 3 (refactoring) based on metrics data.

---

**Status:** PROPOSED  
**Next Steps:**
1. Get approval for revised scope
2. Update issue #880 body
3. Implement Phase 1
4. Gather metrics, evaluate need for Phases 2-3
