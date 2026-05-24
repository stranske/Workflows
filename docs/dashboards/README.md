# Dashboards Directory

This directory contains automated dashboard reports for monitoring repository metrics.

## Available Dashboards

### LangSmith Metrics Dashboard

**File:** `langsmith-metrics.md`
**Workflow:** `.github/workflows/maint-80-langsmith-metrics-dashboard.yml`
**Schedule:** Every Monday at 9:00 AM UTC
**Purpose:** Track LangSmith trace coverage across all LLM operations

#### What It Tracks

- **Overall trace coverage %** - Percentage of LLM calls that captured trace IDs
- **Coverage by operation type** - Breakdown by step/evaluation/generation
- **Coverage by autopilot step** - Per-step analysis for autopilot pipeline
- **Total operations** - Volume of LLM calls

#### Where to View

1. **Dashboard file:** `docs/dashboards/langsmith-metrics.md` (updated weekly, committed to main)
2. **Weekly issues:** Created automatically with label `langsmith,metrics`
3. **Workflow artifacts:** Downloadable JSON + markdown reports (90-day retention)

#### Manual Triggers

Run the workflow manually to generate on-demand reports:

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

The dashboard aggregates metrics from:
- Autopilot workflow artifacts (`autopilot-metrics-*.ndjson`)
- LangSmith fleet artifacts (`langsmith-fleet.ndjson`) registered in
  `config/langsmith_fleet_registry.json`
- 14-day artifact retention window
- All completed autopilot runs in the specified time period

#### How It Works

1. **Download** - Fetches metrics artifacts from recent autopilot runs
2. **Combine** - Merges all NDJSON files into single dataset
3. **Analyze** - Runs `scripts/aggregate_metrics.py` to compute coverage
4. **Validate fleet artifacts** - Runs `scripts/langsmith_fleet.py` against
   `langsmith-fleet/v1` records so the dashboard can distinguish missing,
   invalid, stale, and valid repo artifacts
5. **Report** - Generates markdown report + JSON summary
6. **Publish** - Updates dashboard file, creates issue, uploads artifact

---

## Adding New Dashboards

To create a new dashboard:

1. **Create workflow** in `.github/workflows/maint-XX-<name>-dashboard.yml`
2. **Generate report** as markdown file
3. **Save to** `docs/dashboards/<name>.md`
4. **Update this README** with dashboard details

### Dashboard Workflow Template

```yaml
name: My Dashboard

on:
  schedule:
    - cron: '0 9 * * 1'  # Weekly
  workflow_dispatch:

jobs:
  generate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Generate report
        run: |
          # Your analysis script
          ./scripts/analyze.py > docs/dashboards/my-dashboard.md

      - name: Commit dashboard
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add docs/dashboards/my-dashboard.md
          git commit -m "chore: Update my dashboard"
          git push
```

---

## Related Documentation

- [LangSmith Integration Status](../LANGSMITH_INTEGRATION_STATUS.md)
- [LangSmith E2E Validation](../LANGSMITH_E2E_VALIDATION.md)
- [LangSmith Fleet Record Contract](../contracts/langsmith-fleet-v1.md)
- [Autopilot Metrics Schema](../ci/AUTOPILOT_METRICS_SCHEMA.md)
