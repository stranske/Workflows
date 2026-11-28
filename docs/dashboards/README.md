# Dashboards Directory

## Available Dashboards

### LangSmith Metrics Dashboard

The [dashboard workflow](../../.github/workflows/maint-80-langsmith-metrics-dashboard.yml)
runs Mondays at 09:00 UTC. It reports trace coverage and operation counts overall,
by operation type and by Auto-Pilot step.

#### Where to View

- [Dashboard issue #2415](https://github.com/stranske/Workflows/issues/2415) holds
  the current report and links to its workflow run.
- [Dashboard runs](https://github.com/stranske/Workflows/actions/workflows/maint-80-langsmith-metrics-dashboard.yml)
  retain report Markdown, JSON, diagnostics and NDJSON artifacts for 30 days.
- [Stable dashboard pointer](langsmith-metrics.md) links to the current report
  and observability contract. Scheduled runs leave this repository file unchanged.

#### Manual Triggers

```bash
# Last 7 days (default)
gh workflow run "LangSmith Metrics Dashboard" --repo stranske/Workflows

# Last 30 days with issue
gh workflow run "LangSmith Metrics Dashboard" \
  --repo stranske/Workflows \
  -f days_back=30 \
  -f create_issue=true

# Last 14 days, artifact only (no issue)
gh workflow run "LangSmith Metrics Dashboard" \
  --repo stranske/Workflows \
  -f days_back=14 \
  -f create_issue=false
```

#### Data Sources

- [Trace aggregation](../../scripts/aggregate_metrics.py) reads this repository's
  `agents-verifier-metrics` artifacts from the selected window.
- [Fleet validation](../../scripts/langsmith_fleet.py) combines readable
  `langsmith-fleet.ndjson` artifacts for entries configured to use artifact evidence
  in the [fleet registry](../../config/langsmith_fleet_registry.json). Its token
  needs Actions read access to those repositories. A `missing` row has zero
  records matching the registered repository and surface, even if an artifact
  was downloaded. Matching valid records past the freshness threshold are
  `stale`. [Trip-planner has published a fleet artifact](https://github.com/stranske/trip-planner/actions/runs/44590538130/artifacts/14561744805).

#### How It Works

The fleet section shows `missing`, `invalid`, `stale` and `valid` artifact
statuses, `direct` for central LangSmith evidence, and `not-applicable` for
allowlisted repositories. Missing or invalid rows get warnings. Either data
source can produce a report. When a report is available, the workflow uploads
it as an artifact. On scheduled runs or when `create_issue=true` on manual runs,
it updates the matching open dashboard issue or creates one if none exists.
The default manual invocation includes that issue step. Repository contents
access is read-only.

## Adding New Dashboards

Generate Markdown and machine-readable outputs in a maintenance workflow. Upload
them as artifacts and use one durable issue when readers need an in-place report.
Add a stable pointer in this directory and link it from this index.

### Dashboard Workflow Template

Use the [LangSmith dashboard workflow](../../.github/workflows/maint-80-langsmith-metrics-dashboard.yml)
as the working example for a schedule, manual inputs, artifact upload and issue updates.
Test the generation command and report destinations before publishing a new dashboard.

## Related Documentation

- [LangSmith Integration Status](../LANGSMITH_INTEGRATION_STATUS.md)
- [LangSmith E2E Validation](../LANGSMITH_E2E_VALIDATION.md)
- [LangSmith Fleet Record Contract](../contracts/langsmith-fleet-v1.md)
- [Autopilot Metrics Schema (retired, historical)](../ci/AUTOPILOT_METRICS_SCHEMA.md)
