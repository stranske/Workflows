## Reusable Python CI Workflow

This repository provides a reusable GitHub Actions workflow that layers three progressive phases on top of a minimal test + coverage gate. Advanced observability features remain opt-in. Omitted runtime inputs select the parallel Python 3.13/3.14 matrix; explicit runtime overrides retain precedence.

### Workflow callers

- [Workflows Gate](../.github/workflows/pr-00-gate.yml) calls the local reusable
  in parallel for the main suite and the verifier grammar suites. Both calls
  run Python 3.13 and 3.14 when the applicable CI path is selected. The main
  suite publishes coverage from 3.14 and Gate's `summary` consumes the job
  results and available artifacts.
- The [consumer Gate template](../templates/consumer-repo/.github/workflows/pr-00-gate.yml)
  calls the shared reusable at `@main` for applicable PR checks. The separate
  [consumer CI template](../templates/consumer-repo/.github/workflows/ci.yml)
  calls it on main pushes and by dispatch. The consumer verifier uses that
  push CI as post-merge evidence.
- [Selftest Reusables](ci/SELFTESTS.md) exercises reusable behavior with
  fixtures. The [system map](ci/WORKFLOW_SYSTEM.md#topology-at-a-glance)
  shows how Gate results, fork status publication, Autofix, and verifier
  evidence reach their respective callers and listeners.

### Overview

| Phase | Feature Set | Helper Script | Artifacts |
|-------|-------------|---------------|-----------|
| Base  | Tests + coverage minimum + optional mypy | – | `coverage.xml`, `coverage.json` (internal) |
| 1     | Metrics extraction (parse JUnit) | `scripts/ci_metrics.py` | `ci-metrics.json` |
| 2     | Failure classification + metrics history append | `scripts/ci_history.py` | `metrics-history.ndjson`, `classification.json` |
| 3     | Coverage delta vs baseline | `scripts/ci_coverage_delta.py` | `coverage-delta.json` |

### Inputs

Core:
```
python-version               Explicit single-runtime override (default empty)
python-versions              JSON list override (default []; omitted runtimes select 3.13 and 3.14)
primary-python-version       Artifact/tooling runtime (default shared CI_PYTHON_VERSION when selected, else first selected runtime)
pytest-workers               xdist workers (default auto; first-party Gate requests 4)
coverage-python-version      Optional coverage runtime, matching primary (default empty: all runtimes)
coverage-min                 Minimum coverage percentage to pass (default 70)
run-mypy                     Boolean toggle to run mypy job (default true)
typecheck-paths              Space-separated mypy targets; missing ones dropped, none left -> repo root (default 'src')
```

Gate applies the same full-suite discovery, `not quarantine and not slow` markers,
common `requirements.lock` to both runtimes. Gate measures branch coverage on
3.14 only; 3.13 runs plain pytest with the same selected suite.
The package minimum is Python >=3.13 (3.14 first, 3.13 backup; 3.12 is retired).
An explicit `python-version` still selects only that runtime. Consumer Gates are
create-only, so each consumer moves its own explicit pins.

Phase 1 – Metrics:
```
enable-metrics               Enable metrics extraction (default false)
slow-test-top                Number of slow tests to record (default 15)
slow-test-min-seconds        Minimum seconds for a test to be considered slow (default 1)
```

Phase 2 – History & Classification:
```
enable-history               Append a NDJSON history line (default false)
enable-classification        Emit classification.json with failed/error tests (default false)
history-artifact-name        NDJSON history filename (default metrics-history.ndjson)
```

Phase 3 – Coverage Delta:
```
enable-coverage-delta        Compute coverage delta vs baseline (default false)
baseline-coverage            Baseline coverage percent (default 0 -> treated as no baseline)
coverage-alert-drop          Coverage drop (pct points) for alert/fail (default 1)
fail-on-coverage-drop        Fail job if drop >= threshold (default false)
coverage-drop-label          Placeholder label name for future automation (default coverage-drop)
```

All numeric inputs must be finite: `NaN`, positive infinity, and negative
infinity are rejected during input validation. Coverage percentages
(`coverage-min` and `baseline-coverage`) and `coverage-alert-drop` accept values
from 0 through 100. Slow-test thresholds must be non-negative integers.

### Helper Scripts

#### `scripts/ci_metrics.py`
Parses `pytest-junit.xml` to produce `ci-metrics.json` containing aggregate counts, failure list, and slow test subset.

Environment vars:
```
JUNIT_PATH=pytest-junit.xml
OUTPUT_PATH=ci-metrics.json
TOP_N=15
MIN_SECONDS=1
```

#### `scripts/ci_history.py`
Appends one NDJSON line capturing test counts, optional metrics payload, and (if enabled) a failure classification summary.

Environment vars:
```
JUNIT_PATH=pytest-junit.xml
METRICS_PATH=ci-metrics.json
HISTORY_PATH=metrics-history.ndjson
ENABLE_CLASSIFICATION=true|false
CLASSIFICATION_OUT=classification.json
```

#### `scripts/ci_coverage_delta.py`
Reads `coverage.xml`, derives line coverage percent, compares to `BASELINE_COVERAGE`, and writes `coverage-delta.json`.

Environment vars:
```
COVERAGE_XML_PATH=coverage.xml
OUTPUT_PATH=coverage-delta.json
BASELINE_COVERAGE=75
ALERT_DROP=1
FAIL_ON_DROP=true|false
```

Output schema example:
```json
{
  "current": 78.91,
  "baseline": 80.25,
  "delta": -1.34,
  "drop": 1.34,
  "threshold": 1.0,
  "status": "alert"   // one of no-baseline | ok | alert | fail
}
```

### Artifacts Summary

| Name              | When Enabled | Contents |
|-------------------|--------------|----------|
| ci-metrics        | enable-metrics | Aggregated test metrics JSON |
| coverage-delta    | enable-coverage-delta | Coverage delta JSON report |
| metrics-history   | enable-history | NDJSON appended per run |
| classification    | enable-classification | Failed/error test detail |

### Example Invocation (Reusable Workflow)

For a repo-specific `ci.yml` with post-merge push checks, the example below
uses the first-party `@main` convention.
```yaml
name: CI
on:
  push:
    branches: [main]
  workflow_dispatch:
jobs:
  ci:
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main
    with:
      python-versions: '["3.13", "3.14"]'
      coverage-min: '72'
      enable-metrics: true
      enable-history: true
      enable-classification: true
      enable-coverage-delta: true
      baseline-coverage: '75.5'
      coverage-alert-drop: '1.0'
      fail-on-coverage-drop: true

```

### Monorepo Usage

Set `working-directory` when your project lives in a subfolder. The reusable workflow will run all
`run:` steps from that directory, stage coverage artifacts from the same location, and rely on
sparse checkout to fetch the shared helper scripts it needs:

```yaml
name: Package CI
on:
  push:
    branches: [main]
  workflow_dispatch:
jobs:
  ci:
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main
    with:
      working-directory: packages/my-package
      python-versions: '["3.14"]'
      coverage-min: '80'
```

### Summary Step
The workflow writes a Markdown overview (artifacts presence + coverage stats) into the GitHub Actions run summary using `GITHUB_STEP_SUMMARY`.

### Universal Job Log Table (Issue #1344)
A dedicated `logs_summary` job runs after ordinary success or failure (even if advanced phases are disabled), but skips whole-workflow cancellation using `always() && !cancelled()`. When it runs, it appends a per-job log links table plus a brief success/failure explanation. This makes it easy to jump directly to failing job logs without enabling any optional features. The soft coverage gate job no longer duplicates the table.

### Coverage Soft Gate & Topology Cross-Links (Issue #1351)
Set `enable-soft-gate: true` when the caller needs the soft coverage path.
Use the [Gate job map](ci/WORKFLOWS.md#gate-job-map) to trace the aggregate
check and the [workflow outputs reference](ci/WORKFLOW_OUTPUTS.md) to see
how reusable workflow output contracts differ from job results and artifacts.

### Design Principles
1. Backward compatible defaults (all advanced phases off).
2. External Python helpers to prevent YAML bloat and parsing errors.
3. Small, composable artifacts; no large multi-purpose logs.
4. Fail fast only on explicit user intent (e.g. `fail-on-coverage-drop`).

### Future Enhancements (Planned / Candidates)
* Label application for coverage drops using `coverage-drop-label`.
* Regex-driven failure categorization (flaky, infra, timeout, assertion).
* Metrics trend regression detection (auto flag large variance vs trailing median).
* Slack/Teams summarizer job (out-of-repo dispatch) using artifacts.

---

### Local Style Checks Mirror

To ensure your branch will pass the CI style/lint checks (with pinned versions), run:

```bash
./scripts/dev_check.sh
```

If you need a faster subset (or want to run individual checks), see [docs/validation/overview.md](validation/overview.md).

### Optional Pre-Push Hook

Follow the [Git hooks installation guide](git-hooks/overview.md#installation)
to install the configured pre-commit and pre-push hooks. To run a push check
by hand, use the [stage-specific commands](git-hooks/overview.md#manual-hook-execution).

Last updated: 2026-01-11 (update when modifying workflow inputs or scripts).
