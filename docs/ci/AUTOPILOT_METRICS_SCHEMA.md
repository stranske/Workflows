# Auto-Pilot Metrics Schema

Auto-pilot metrics are logged as newline-delimited JSON (NDJSON), one record per
line. Each record describes either a step execution, a cycle summary, or an
escalation event. The schema version is encoded in the collector output and is
listed here for reference.

## Schema Version

- `version`: 1

## Common Fields

All record types include the following fields:

- `schema_version`: Integer schema version (currently `1`).
- `metric_type`: `"step"`, `"cycle"`, or `"escalation"`.
- `issue_number`: Integer issue number.
- `timestamp`: ISO 8601 UTC timestamp for the record.
- `cycle_count`: Integer cycle counter for the auto-pilot run.
- `langsmith_trace_id` (optional): LangSmith trace identifier when tracing is enabled.
- `langsmith_trace_url` (optional): Clickable LangSmith trace URL for the run.

The metrics collector always writes NDJSON records to the configured log file **and**
prints the JSON record to stdout for CI visibility.

## Log Output Paths

- `--path`: Explicit NDJSON output path (default: `autopilot-metrics.ndjson`).
- `AUTOPILOT_METRICS_LOG_PATH`: Environment override for the default output path.
- `AUTOPILOT_METRICS_SUMMARY_PATH`: Optional NDJSON summary output for failures
  emitted by the metrics collector and step timer utilities.

## Step Record (`metric_type: "step"`)

Required fields:

- `step_name`: String step identifier (e.g., `format-issue`).
- `duration_ms`: Integer duration in milliseconds.
- `success`: Boolean success flag.
- `failure_reason`: String failure reason; use `"none"` when `success` is true.

Edge cases:

- When `success` is `false`, `failure_reason` must be a non-empty string.
- When `success` is `true`, `failure_reason` is normalized to `"none"`.
- If `duration_ms` is omitted, provide `started_at`/`ended_at` or
  `started_at_ms`/`ended_at_ms` to derive duration.

Example:

```json
{
  "schema_version": 1,
  "metric_type": "step",
  "issue_number": 120,
  "timestamp": "2026-02-01T12:34:56Z",
  "cycle_count": 2,
  "langsmith_trace_id": "trace_abc123",
  "langsmith_trace_url": "https://smith.langchain.com/r/trace_abc123",
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
  "schema_version": 1,
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
  "schema_version": 1,
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

## Failure Summary Records

When `AUTOPILOT_METRICS_SUMMARY_PATH` is set, failures in the metrics collector or
step timer append a summary record describing the error. These records are **not**
validated by the main schema, but provide observability in CI logs.

Fields:

- `summary_type`: `"autopilot-metrics-error"`.
- `component`: `"autopilot_metrics_collector"` or `"autopilot_step_timer"`.
- `timestamp`: ISO 8601 UTC timestamp of the failure.
- `step_name`: Step identifier (from `AUTOPILOT_STEP_NAME` when available).
- `metric_type`: The metric type being emitted (when available).
- `error_category`: Error classification (defaults to `validation_error` or `timer_error`,
  override with `AUTOPILOT_ERROR_CATEGORY`).
- `exit_code`: Process exit code.
- `message`: Failure message.
- `environment`: Selected CI environment details (run ID, workflow, job, ref, SHA).

Example:

```json
{
  "summary_type": "autopilot-metrics-error",
  "component": "autopilot_metrics_collector",
  "timestamp": "2026-02-01T12:46:02Z",
  "step_name": "format",
  "metric_type": "step",
  "error_category": "validation_error",
  "exit_code": 1,
  "message": "duration_ms is required unless started_at or started_at_ms is set",
  "environment": {
    "github_run_id": "123456",
    "github_workflow": "Agents Auto-Pilot",
    "github_job": "auto-pilot",
    "github_ref": "refs/heads/main",
    "github_sha": "..."
  }
}
```

## Keepalive Dispatch Token Handling

Keepalive dispatch uses the same token priority as the main keepalive instruction
author. If no dedicated dispatch token is provided, the runner falls back to the
instruction author token to avoid silent dispatch failures. This behavior is
validated in the keepalive runner unit tests.

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
