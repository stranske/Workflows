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
| `ci-reference.json` | Reused GitHub Actions receipts from PR #4172 |

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
