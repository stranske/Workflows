# Metrics Developer Guide

This guide explains how to add new metrics to the dashboard pipeline, from
emitting per-repo NDJSON to updating aggregation, dashboards, and tests.

## Pipeline overview

1. Per-repo metrics are logged as NDJSON (one JSON object per line).
2. `scripts/aggregate_repo_metrics.py` combines per-repo logs into a single
   NDJSON file and writes a summary JSON.
3. `scripts/metrics_dashboard_generator.py` reads the combined NDJSON and
   produces a markdown dashboard (default: `docs/metrics/WEEKLY_DASHBOARD.md`).

## Metric record format

Each metrics entry should be a flat JSON object with a timestamp and numeric
fields. The aggregator adds `repo` tags and emits aggregate entries for grouped
fields.

Minimal example:

```json
{"timestamp": "2024-01-01T00:00:00Z", "metric_name": "ci_runtime", "workflow": "ci", "dimension": "total", "duration_ms": 120000, "success_rate": 98.5}
```

Recommended fields:

- `timestamp` (ISO 8601; the dashboard also recognizes `recorded_at`, `created_at`,
  `time`, or `run_started_at`)
- `metric_name`, `workflow`, `dimension` (used for grouping aggregate output)
- One or more numeric fields (float/int values, or numeric strings)

## Where metrics live

- Per-repo logs live under the metrics directory (default `repo-metrics/`) and
  are named `owner__repo.ndjson`.
- The aggregate step writes:
  - Combined NDJSON: `combined-repo-metrics.ndjson`
  - Summary JSON: `repo-metrics-summary.json`
- The dashboard generator writes `docs/metrics/WEEKLY_DASHBOARD.md` by default.

## Adding a new metric

1. **Emit the metric** in the metrics producer so it appears in the per-repo
   NDJSON. Use numeric values for fields that should be charted.
2. **Aggregate the metric** by passing `--numeric-field <field>` to
   `scripts/aggregate_repo_metrics.py` (repeatable). If you omit numeric fields,
   the script infers them from the data.
3. **Update dashboard fields** by passing `--fields <field>` to
   `scripts/metrics_dashboard_generator.py`, or set `numeric_fields` in the
   optional config JSON file.
4. **Add thresholds** (optional) by adding a `thresholds` block in the config
   file so the dashboard status column renders `OK/WARN/FAIL`.
5. **Update fixtures and tests** so the E2E pipeline remains deterministic.

## Dashboard configuration

The dashboard generator accepts an optional JSON config file with these keys:

- `metrics_path`: path to the combined NDJSON
- `output_path`: path to the markdown dashboard
- `numeric_fields`: list of numeric field names to display
- `thresholds`: map of field name to `ok`, `warn`, and `higher_is_better`

Example config:

```json
{
  "metrics_path": "combined-repo-metrics.ndjson",
  "output_path": "docs/metrics/WEEKLY_DASHBOARD.md",
  "numeric_fields": ["duration_ms", "success_rate", "failed_jobs"],
  "thresholds": {
    "success_rate": {"ok": 98, "warn": 95, "higher_is_better": true},
    "duration_ms": {"ok": 120000, "warn": 150000, "higher_is_better": false}
  }
}
```

## Updating tests

- Add new fixture values in `tests/fixtures/sample_metrics.json`.
- Update `tests/e2e/test_metrics_dashboard.py` assertions if the new metric is
  required for the pipeline.
- For dashboard logic changes, update unit tests in
  `tests/scripts/test_metrics_dashboard_generator.py`.

## Quick validation

From the repo root:

```bash
python scripts/aggregate_repo_metrics.py --repos owner/repo --metrics-dir repo-metrics \
  --output combined-repo-metrics.ndjson --summary-output repo-metrics-summary.json \
  --numeric-field duration_ms
python scripts/metrics_dashboard_generator.py --path combined-repo-metrics.ndjson \
  --output docs/metrics/WEEKLY_DASHBOARD.md --fields duration_ms
```

