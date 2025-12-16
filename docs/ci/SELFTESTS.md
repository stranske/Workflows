# Self-Test Workflow Overview

The repository exposes a single canonical self-test workflow named **Selftest: Reusables**. It is scheduled nightly (`30 6 * * *`) and can also be launched manually through the *workflow_dispatch* form. The workflow fans out to the shared Python CI reusable (`reusable-10-ci-python.yml`) so each scenario runs the same matrix that exercises Pull Request CI, while keeping dispatch logic in one place.

## Triggers

| Trigger | Description |
|---------|-------------|
| Nightly cron | Executes at 06:30 UTC and records the verification table in the run summary. |
| Manual dispatch | Allows custom run reasons, comment mode, and optional report retrieval through the workflow inputs. |

Manual runs support three presentation modes:
- `summary` (default) – write the condensed matrix table to the run summary.
- `comment` – post the same table as a pull-request comment (requires `post_to: pr-number` and a PR ID).
- `dual-runtime` – shorthand that requests both Python 3.11 and 3.12 without editing the JSON input.

## Scenario Matrix

The workflow executes six scenarios with `strategy.fail-fast: false` so failures in one combination do not cancel the others. Each scenario prefixes artifacts with `sf-<scenario>-`.

| Scenario | Metrics | History | Classification | Coverage Δ | Soft Gate | Notes |
|----------|---------|---------|----------------|------------|-----------|-------|
| `minimal` | ❌ | ❌ | ❌ | ❌ | ❌ | Smoke validation of the reusable CI executor. |
| `metrics_only` | ✅ | ❌ | ❌ | ❌ | ❌ | Exercises metrics collection without history uploads. |
| `metrics_history` | ✅ | ✅ | ❌ | ❌ | ❌ | Adds report-history artifacts. |
| `classification_only` | ❌ | ❌ | ✅ | ❌ | ❌ | Validates classification exports in isolation. |
| `coverage_delta` | ❌ | ❌ | ❌ | ✅ | ❌ | Checks coverage comparison thresholds (baseline 65%, alert drop 2%). |
| `full_soft_gate` | ✅ | ✅ | ✅ | ✅ | ✅ | Full verification including soft gate enforcement artifacts. |

## Runtime and History Controls

- **Python versions** – leave blank to run only 3.11. Provide a JSON array (for example `['3.11','3.12']`) or choose the `dual-runtime` mode to exercise both interpreters.
- **History toggle** – set the `enable_history` input to `true` when launching manually if you want the workflow to download the generated `selftest-report` artifact automatically.
- **Run reason** – optionally describe why the self-test was dispatched; this string is echoed back in both the run summary and any PR comment the workflow posts.

## Outputs and Summary

The `Aggregate & Verify` job collects artifacts for every scenario, renders a compact table, and uploads a consolidated `selftest-report.json` artifact. The report captures:
- Workflow run identifier.
- Python versions used for the matrix.
- Scenario-by-scenario status plus any missing or unexpected artifacts.
- Total artifact count and failure tally.

The same data is written to `GITHUB_STEP_SUMMARY` as a Markdown table so the Actions UI always exposes a quick status snapshot. When comment mode is selected, the workflow posts that table (and overall status) directly on the target pull request.

## Maintenance Notes

- This document replaces the legacy self-test workflow guidance that referenced `selftest-runner.yml` and the `maint-4x` wrappers. Historical context remains in [`ARCHIVE_WORKFLOWS.md`](../archive/ARCHIVE_WORKFLOWS.md).
- The reusable workflow contract lives in `.github/workflows/reusable-10-ci-python.yml`. Update the scenario expectations here whenever the reusable job starts producing additional artifacts.
- Keep the artifact prefixes stable (`sf-<scenario>-...`) so verification logic continues to match expected uploads.
