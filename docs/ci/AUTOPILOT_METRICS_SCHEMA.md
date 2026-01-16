# Auto-Pilot Metrics Schema

Auto-pilot metrics are logged as newline-delimited JSON (NDJSON), one record per
line. Each record describes either a step execution, a cycle summary, or an
escalation event. The schema version is encoded in the collector output and is
listed here for reference.

## Schema Version

- `version`: 1

## Common Fields

All record types include the following fields:

- `metric_type`: `"step"`, `"cycle"`, or `"escalation"`.
- `issue_number`: Integer issue number.
- `timestamp`: ISO 8601 UTC timestamp for the record.
- `cycle_count`: Integer cycle counter for the auto-pilot run.

## Step Record (`metric_type: "step"`)

Required fields:

- `step_name`: String step identifier (e.g., `format-issue`).
- `duration_ms`: Integer duration in milliseconds.
- `success`: Boolean success flag.
- `failure_reason`: String failure reason; use `"none"` when `success` is true.

Example:

```json
{
  "metric_type": "step",
  "issue_number": 120,
  "timestamp": "2026-02-01T12:34:56Z",
  "cycle_count": 2,
  "step_name": "format-issue",
  "duration_ms": 3142,
  "success": true,
  "failure_reason": "none"
}
```

## Cycle Record (`metric_type: "cycle"`)

Optional fields:

- `max_cycles`: Integer max cycles configured for auto-pilot.
- `steps_attempted`: Integer count of steps attempted in the cycle.
- `steps_completed`: Integer count of steps completed in the cycle.

Example:

```json
{
  "metric_type": "cycle",
  "issue_number": 120,
  "timestamp": "2026-02-01T12:40:10Z",
  "cycle_count": 2,
  "max_cycles": 6,
  "steps_attempted": 4,
  "steps_completed": 3
}
```

## Escalation Record (`metric_type: "escalation"`)

Required fields:

- `escalation_reason`: String description (for example, `needs-human label applied`).

Example:

```json
{
  "metric_type": "escalation",
  "issue_number": 120,
  "timestamp": "2026-02-01T12:45:01Z",
  "cycle_count": 2,
  "escalation_reason": "needs-human label applied"
}
```

## Schema Output

To output the JSON schema from the collector:

```bash
python scripts/autopilot_metrics_collector.py --print-schema
```

## Needs Human Action

Auto-pilot step timing still requires workflow edits in `.github/workflows/agents-auto-pilot.yml`
to call `scripts/autopilot_step_timer.py` at the start/end of each step and pass the
timestamps to `scripts/autopilot_metrics_collector.py` (for example via `--started-at-ms`
and `--ended-at-ms`). Workflow files are protected in agent-standard runs, so a
maintainer must apply the timing-step additions and label the PR `needs-human`.

## Interpreting Metrics

Use the records together to answer three questions: how long each step takes,
how often steps fail, and when human escalation occurs.

- **Step timing**: For each `step` record, `duration_ms` captures elapsed time
  for that step. High `duration_ms` outliers point to bottlenecks; compare
  medians across runs to separate noisy spikes from systemic slowness.
- **Step success**: `success` plus `failure_reason` explain failure modes.
  Aggregate by `failure_reason` to identify recurring blockers (e.g., parser
  errors vs. external service timeouts).
- **Cycle health**: `cycle` records summarize overall progress per run. When
  `steps_attempted` is high but `steps_completed` is low, investigate the
  failing step name(s) for that cycle.
- **Escalation signals**: `escalation` records show when auto-pilot stopped and
  required human intervention. Track escalation rate and correlate with
  `failure_reason` to prioritize fixes that reduce handoffs.
