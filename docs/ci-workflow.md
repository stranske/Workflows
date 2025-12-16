## Reusable Python CI Workflow

This repository provides a reusable GitHub Actions workflow that layers three progressive phases on top of a minimal test + coverage gate. All advanced features are opt‑in so existing callers remain unaffected until they enable them.

> **Note (Issue #2656):** The in-repo Gate workflow now calls `reusable-10-ci-python.yml` for Python 3.11/3.12 alongside the Docker smoke reusable. The former matrix wrapper (`reusable-90-ci-python.yml`) was retired during the CI consolidation; downstream consumers should invoke `reusable-10-ci-python.yml` directly or dispatch `selftest-reusable-ci.yml` when they need a matrix verification sweep. Historical notes about the removed wrapper live in [ARCHIVE_WORKFLOWS.md](archive/ARCHIVE_WORKFLOWS.md).

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
python-versions              JSON list of Python versions (default ["3.11"]) 
coverage-min                 Minimum coverage percentage to pass (default 70)
run-mypy                     'true'/'false' toggle to run mypy job (default true)
```

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

In a caller repository `.github/workflows/ci.yml` (older wrappers used `pr-10-ci-python.yml`
before the Gate consolidation—see [ARCHIVE_WORKFLOWS.md](archive/ARCHIVE_WORKFLOWS.md) for the
retirement log):
```yaml
name: Project CI
on: [push, pull_request]
jobs:
  ci:
    uses: owner-or-fork/Trend_Model_Project/.github/workflows/reusable-10-ci-python.yml@main
    with:
      python-versions: '["3.11", "3.12"]'
      coverage-min: '72'
      enable-metrics: 'true'
      enable-history: 'true'
      enable-classification: 'true'
      enable-coverage-delta: 'true'
      baseline-coverage: '75.5'
      coverage-alert-drop: '1.0'
      fail-on-coverage-drop: 'true'
```

### Summary Step
The workflow writes a Markdown overview (artifacts presence + coverage stats) into the GitHub Actions run summary using `GITHUB_STEP_SUMMARY`.

### Universal Job Log Table (Issue #1344)
A dedicated `logs_summary` job runs on every workflow execution (even if advanced phases are disabled) and appends a per-job log links table plus a brief success/failure explanation. This makes it easy to jump directly to failing job logs without enabling any optional features. The soft coverage gate job no longer duplicates the table.

### Coverage Soft Gate & Topology Cross-Links (Issue #1351)
For the broader CI topology (gate aggregation job, temporary wrapper, Codex kickoff lifecycle, and migration plan) see `.github/workflows/README.md` sections 1.1 and 7.2–7.6. This document intentionally avoids repeating those operational details; it focuses on the reusable workflow inputs and helper scripts. Enable the soft coverage gate in a consumer by passing `enable-soft-gate: 'true'` (documented in README section 7.3).

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

To ensure your branch will pass the CI style job (Black + Ruff with pinned versions), run:

```bash
./scripts/style_gate_local.sh
```

This script loads version pins from `.github/workflows/autofix-versions.env`, installs them in the active (or ad-hoc) environment, and performs:

- `black --check .`
- `ruff check .`
- `mypy --config-file pyproject.toml src/trend_analysis src/trend_portfolio_app`

If either fails, apply fixes:
```bash
black .
ruff check --fix .
# address any mypy findings the script surfaced
```

### Optional Pre-Push Hook

Install a git pre-push hook that blocks pushes when the CI style checks fail:

```bash
mkdir -p .git/hooks
cat > .git/hooks/pre-push <<'EOF'
#!/usr/bin/env bash
# Abort push if CI style checks fail
scripts/style_gate_local.sh || {
  echo "[pre-push] CI style checks failed; push aborted." >&2
  exit 1
}
EOF
chmod +x .git/hooks/pre-push
```

Add this to your personal workflow; we do not version-control the hook file itself to avoid surprising contributors. For team-wide enforcement, a wrapper installer can be added to `scripts/git_hooks.sh` (future enhancement).

Last updated: 2026-11-11 (update when modifying workflow inputs or scripts).
