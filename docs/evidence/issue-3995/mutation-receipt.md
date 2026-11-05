# Mutation receipts for #3995 closer repair

Checked 2026-11-03. Each row is a deliberate production mutation, named failing test, and restored pass.

## legacy ndjson fallback
- Break: `scripts/aggregate_agent_metrics.py`
- RED exit: 1
```
E         
E         At index 0 diff: [] != [{'metric_type': 'keepalive'}]
E         Use -v to get more diff

tests/scripts/test_aggregate_agent_metrics.py:2027: AssertionError
=========================== short test summary info ============================
FAILED tests/scripts/test_aggregate_agent_metrics.py::test_uncovered_metric_helpers_preserve_legacy_and_error_contracts
1 failed in 0.26s
```
- GREEN: 1 passed in 0.22s

## empty repos preflight
- Break: `scripts/check_consumer_sync_drift.py`
- RED exit: 1
```
E        +    where <function main at 0x110f43880> = check_consumer_sync_drift.main

tests/scripts/test_check_consumer_sync_drift.py:1372: AssertionError
----------------------------- Captured stdout call -----------------------------
::error::No repos provided or found in REGISTERED_CONSUMER_REPOS
=========================== short test summary info ============================
FAILED tests/scripts/test_check_consumer_sync_drift.py::test_main_writes_actionable_reports_for_early_preflight_failures
1 failed in 0.31s
```
- GREEN: 1 passed in 0.21s

## invalid manifest error
- Break: `scripts/check_consumer_sync_drift.py`
- RED exit: 1
```
tests/scripts/test_check_consumer_sync_drift.py:1415: AssertionError
----------------------------- Captured stdout call -----------------------------
::error::Manifest is invalid — refusing to run drift check:
1 manifest validation error(s):
  - bad manifest
=========================== short test summary info ============================
FAILED tests/scripts/test_check_consumer_sync_drift.py::test_main_rejects_invalid_configuration_and_unusable_tokens
1 failed in 0.27s
```
- GREEN: 1 passed in 0.23s

## converged main success
- Break: `scripts/check_consumer_sync_drift.py`
- RED exit: 1
```
E        +    where <function main at 0x10bbbf880> = check_consumer_sync_drift.main

tests/scripts/test_check_consumer_sync_drift.py:1484: AssertionError
----------------------------- Captured stdout call -----------------------------
Consumer repos are in sync.
=========================== short test summary info ============================
FAILED tests/scripts/test_check_consumer_sync_drift.py::test_main_compares_manifest_files_and_writes_converged_summary
1 failed in 0.27s
```
- GREEN: 1 passed in 0.22s

## header insensitive compare
- Break: `scripts/check_consumer_sync_drift.py`
- RED exit: 1
```
E        +    where <function main at 0x113dc7880> = check_consumer_sync_drift.main

tests/scripts/test_check_consumer_sync_drift.py:1532: AssertionError
----------------------------- Captured stdout call -----------------------------
::warning::Consumer repo drift detected
=========================== short test summary info ============================
FAILED tests/scripts/test_check_consumer_sync_drift.py::test_main_reports_body_drift_but_ignores_syncer_header_differences
1 failed in 0.28s
```
- GREEN: 1 passed in 0.33s

