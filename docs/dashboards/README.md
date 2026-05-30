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

The dashboard aggregates two distinct data sources, fetched in this workflow:

1. **Trace-coverage metrics** — artifacts from this repo's own completed runs,
   matched by name `autopilot-metrics-*` and `agents-verifier-metrics`
   (`agents-auto-pilot.yml` and `reusable-agents-verifier.yml`), within the
   `days_back` window. These feed `scripts/aggregate_metrics.py`.
2. **LangSmith fleet artifacts** (`langsmith-fleet.ndjson`) — one per repo
   registered in `config/langsmith_fleet_registry.json`. The workflow attempts a
   **cross-repo artifact download** for each registered repo and combines what it
   finds. The token used for the dashboard run must have `actions:read` access to
   each registered repo; otherwise the best-effort lookup records that repo as
   `missing` because the artifact cannot be read. A registered repo with no
   current readable artifact is reported as `missing`, not a job failure. (As of
   this writing, no consumer repo uploads a `langsmith-fleet.ndjson` yet, so most
   rows render `missing` — that honest "pending adoption" state is the point.)

The fleet artifacts follow a contract-first design: Workflows owns the
`langsmith-fleet/v1` schema, registry, validator, and dashboard rollup, while
each consumer repo owns its local emitter and domain instrumentation. See
[`docs/contracts/langsmith-fleet-v1.md`](../contracts/langsmith-fleet-v1.md)
before treating a consumer-local validator as a design blocker.

#### How It Works

1. **Download trace metrics** - Fetches `autopilot-metrics-*` /
   `agents-verifier-metrics` artifacts from recent runs and merges their NDJSON
2. **Validate fleet artifacts** - Downloads each registered repo's
   `langsmith-fleet.ndjson` (best-effort, cross-repo; requires `actions:read` on
   the registered repos) and runs
   `scripts/langsmith_fleet.py --summary --format markdown` against the registry,
   producing a per-repo status table that distinguishes `missing`, `invalid`,
   `stale`, and `valid`. Any `invalid`/`missing` repo raises a `::warning`
   (warning-only — it never hard-fails the dashboard)
3. **Analyze** - Runs `scripts/aggregate_metrics.py` to compute trace coverage
   (when trace metrics exist for the window)
4. **Report** - Generates a markdown report combining the trace-coverage section
   and the fleet artifact status section (the report is published even when only
   the fleet section has content)
5. **Publish** - Updates `docs/dashboards/langsmith-metrics.md`, creates the
   weekly issue, and uploads artifacts (report + fleet status JSON/markdown)

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
