# Issue #4170 closer repair evidence

Merged implementation lives in PR #4172 (`cbad3c6f0`). This directory records the
remaining closer-lane acceptance work: break-and-revert traceability for every test
node added in that PR on the three ranked modules, plus pytest receipts.

## Files

| File | Purpose |
| --- | --- |
| `run_break_and_revert.py` | Re-runs all 24 deliberate production mutations and writes the manifest |
| `break-and-revert-manifest.json` | Per node ID: behavior broken, red/green exit codes and summaries |
| `pytest-three-modules.log` | `pytest -q` on the three `#4172` test modules (112 tests) |
| `pytest-ci-markers.log` | Local full suite with `-m 'not quarantine and not slow'` (see `pytest-ci-markers-summary.txt`) |
| `pytest-ci-markers-summary.txt` | One-line interpreter/result summary for the full-suite run |
| `ci-reference.json` | CI pytest execution receipt plus historical PR #4172 receipts |

## Re-run

```bash
/opt/anaconda3/bin/python3 docs/evidence/issue-4170/run_break_and_revert.py
/opt/anaconda3/bin/python3 -m pytest -q \
  tests/scripts/test_docs_drift_fix_agent.py \
  tests/scripts/test_export_keepalive_durability.py \
  tests/scripts/test_workflow_startup_failure_diagnostic.py
```

## Continuation acceptance (2026-11-05)

Outcome: 24 offline red/restore/green proofs, 112 target-module tests passing,
and a successful CI pytest job demonstrably executing all three modules.
Acceptance commands: the two commands in Re-run above; focused runner checks:
`/opt/anaconda3/bin/python3 -m pytest -q tests/scripts/test_issue_4170_mutation_runner.py`.
Stop rule: stop after three failed attempts at the same step or 60 minutes elapsed;
report the first broken step. No unrelated repairs.

Local verification: runner printed `{"proofs": 24, ...}`; all manifest entries
have red exit 1 and green exit 0, and restored production SHA256 values match.
Three-module pytest: 112 passed. Focused runner checks: 10 passed.
The numeric-limit tests use a temporary offline payload and export destination.
The normal `artifacts/langsmith` tree was absent before and after the proof run;
no normal export was created or changed.

## Follow-ups outside this acceptance repair

- Distinguish pytest exit-1 setup/teardown errors from assertion failures in future
  runner invocations. All 24 current red summaries report failed tests, not errors.
- Extend the runner success-path test to assert manifest field contents; this
  repair verifies exit rejection and restoration, and separately checks all
  recorded manifest exits and production hashes.

The absolute local rerun interpreter is intentional owner direction. CI uses
its configured Python 3.13/3.14 environments.

## Verified CI pytest receipt (2026-11-05)

Tested revision: `4643e9e7df956661716c1b58fe0fff04ac874e68`.
[Gate run 42054217411, attempt 1](https://github.com/stranske/Workflows/actions/runs/42054217411),
[job 127342058378: python ci / python 3.13](https://github.com/stranske/Workflows/actions/runs/42054217411/job/127342058378)
succeeded on Python 3.13.17. The actual pytest step succeeded; this is not an
aggregate or skipped job. Python 3.14 job 127342058150 also succeeded.

Logged shell invocation: `pytest -p ci_test_growth "${args[@]}"`. Expanded from
the checked workflow and logged environment:

```bash
pytest -p ci_test_growth -m 'not quarantine and not slow' --junitxml=pytest-junit.xml --no-cov -n auto --dist load -n 4 --dist=loadgroup
```

Result: `50319 passed, 27 skipped, 3 xfailed in 664.65s (0:11:04)`.
Downloaded artifact `gate-coverage-3.13-1` (13430092357) contains JUnit results:
50 passed in `test_docs_drift_fix_agent.py`, 20 in
`test_export_keepalive_durability.py`, and 42 in
`test_workflow_startup_failure_diagnostic.py`: **112 passed, zero failures,
errors, or skips** across the three targets. `ci-target-junit.xml` preserves
those exact testcase elements; `ci-reference.json` records the source JUnit hash.
The job's step name mentions coverage, but coverage instrumentation was disabled.
