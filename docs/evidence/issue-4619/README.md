# Issue #4619 — Gate python ci / python 3.13 Duration Reduction & Health 85 Tracking

## Context & Objectives
Issue #4619 identified an extreme duration bottleneck in `python ci / python 3.13` (38.40 min in run 41771220527), causing trailing-7-day Gate p50 to exceed the 10-minute budget target (measured at 11.24 min).

## Root Cause Analysis
- **Run URL:** https://github.com/stranske/Workflows/actions/runs/41771220527
- **Job ID:** `126381546540`
- **Head SHA:** `9784a90013c9cc9ce5a0269d781ed3ab16e6ffed` (PR #4438)
- **Bottleneck:** `Pytest (unit tests with coverage)` ran for 2,256.81s (37m 36s). Template parity assertions on large managed files (specifically `scripts/langchain/pr_verifier.py` >150 KB) asserted raw byte equality. On assertion failure, pytest's assertion rewriting invoked `difflib.ndiff`, hanging worker processes for 1,752s–1,902s.

## Bounded Implementation
- Guarded template parity assertions on large synced files with SHA-256 digest-first assertions:
  - `tests/scripts/test_pr_verifier_sync_manifest.py`
  - `tests/scripts/test_native_capacity_registry.py`
  - `tests/workflows/test_keepalive_authority_delivery.py`
  - `tests/workflows/test_repeat_verification_lifecycle.py`
  - `tests/tools/test_verifier_request_correlation.py`
- Added regression test `test_synced_large_file_parity_checks_guard_against_difflib_hangs` in `tests/test_ci_gate_budget.py`.
- Documented requirement in `docs/ci/WORKFLOWS.md`.

## Focused Acceptance Check
- **Command:** `pytest tests/test_ci_gate_budget.py tests/scripts/test_pr_verifier_sync_manifest.py tests/scripts/test_native_capacity_registry.py`
- **Check Date:** 2026-11-10
- **Duration & Result:** `71 passed, 149 skipped in 1.21s` (well within the 2-minute bounded limit).

## Live Gate Before / After Comparison
- **Pre-change Run (41771220527):**
  - Head: `9784a90013c9cc9ce5a0269d781ed3ab16e6ffed`
  - `python ci / python 3.13`: 38m 24s (2,304s total, 2,256s in pytest)
  - Result: failure / timed out workers
- **Post-change Run (42820421600):**
  - Head: `2c5e646cf6c2f7425997c4e4d7c2001dafe385b1`
  - `python ci / python 3.13`: 5m 49s (349s total, 298s in pytest) — **84.8% reduction**
  - `python ci grammar / python 3.13`: 2m 04s (124s total, 102s in pytest)
  - Gate total duration: 7m 44s (464s) — **below 10 min target**
  - Result: success across all 44 jobs

## Health 85 Daily Observations Series (2026-11-04 to 2026-11-10)
Health 85 is workflow id `387854305` (`Health 85 CI Time Budget`, `.github/workflows/health-85-ci-time-budget.yml`).
Published report inspected: `stranske/Workflows@ci-time-budget:docs/reports/ci-budget.json` blob `f06d6f3fd0aa301b320cece179f97a8ef3c02aa7` (commit `06b72b2ff4226c3dda82c693ff435a29b93d5d6f`).

| Date | p50 minutes | p50 seconds | Within 600s | Health 85 run |
| --- | ---: | ---: | --- | --- |
| 2026-11-04 | 11.85 | 711.0 | no | https://github.com/stranske/Workflows/actions/runs/41822549611 |
| 2026-11-05 | missing | missing | no | https://github.com/stranske/Workflows/actions/runs/42020576555 |
| 2026-11-06 | missing | missing | no | https://github.com/stranske/Workflows/actions/runs/42211705537 |
| 2026-11-07 | missing | missing | no | https://github.com/stranske/Workflows/actions/runs/42369018128 |
| 2026-11-08 | missing | missing | no | https://github.com/stranske/Workflows/actions/runs/42476617447 |
| 2026-11-09 | missing | missing | no | https://github.com/stranske/Workflows/actions/runs/42610608867 |
| 2026-11-10 | 11.133333333333333 | 668.0 | no | https://github.com/stranske/Workflows/actions/runs/42838942059 |

### Reproducing the Retained Evidence & Reconciliation
Evaluate the 7-day Health 85 series:
```bash
python -m scripts.health85_budget_observations 
  --workflows workflows.json 
  --observations docs/evidence/issue-4619/health85-daily-observations.json 
  --output docs/evidence/issue-4619/ci-budget-report.json 
  --report-blob-sha f06d6f3fd0aa301b320cece179f97a8ef3c02aa7 
  --issue 4619
```

Reconcile completion status:
```bash
python -m scripts.issue_4619_completion 
  --issue-view docs/evidence/issue-4619/issue-view-4619.json 
  --gate-evidence docs/evidence/issue-4619/gate-run-42820421600.json 
  --budget docs/evidence/issue-4619/ci-budget-report.json 
  --output docs/evidence/issue-4619/completion-reconciliation.json 
  --checked-on 2026-11-10
```

### Status of Sustained Gate (A4)
Current trailing-7-day Gate p50 is 11.13 min (668.0s, down from 11.24 min / 674.5s earlier on 2026-11-10) because pre-fix runs remain in the 7-day window, and 2026-11-05 through 2026-11-09 lack valid measurements. `completion-reconciliation.json` records `action=leave_incomplete` and leaves the sustained-performance acceptance criterion unchecked until Health 85 reports seven consecutive daily measurements <= 10 min.
