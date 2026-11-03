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
