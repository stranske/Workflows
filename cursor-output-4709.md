## Deliberate break → revert (acceptance criterion 2)

Reverted the ordering key in `check_run_is_newer` at `scripts/check_checks_reported.py` (~1292) to stamp-only comparison `(timestamp or "", id)` with no timestampless queued handling—the pre-fix behavior.

### Broken head (`check_run_is_newer` reverted)

```text
$ python3 -m pytest tests/test_check_checks_reported.py::test_queued_check_without_timestamp_blocks_older_pass -q
F                                                                        [100%]
=================================== FAILURES ===================================
____________ test_queued_check_without_timestamp_blocks_older_pass _____________

    def test_queued_check_without_timestamp_blocks_older_pass():
        old_pass = check(ident=1, started="2026-10-01T01:00:00Z")
        pending = queued_check(ident=2)
        for checks in ([old_pass, pending], [pending, old_pass]):
            result = verdict(checks=checks)
>           assert result["verdict"] == "FAIL"
E           AssertionError: assert 'PASS' == 'FAIL'
E             
E             - FAIL
E             + PASS

tests/test_check_checks_reported.py:207: AssertionError
=========================== short test summary info ============================
FAILED tests/test_check_checks_reported.py::test_queued_check_without_timestamp_blocks_older_pass - AssertionError: assert 'PASS' == 'FAIL'
  
  - FAIL
  + PASS
1 failed in 0.23s
```

Observed: id=1 completed success selected, overall verdict `PASS` (regression).

### Restored fix

```text
$ python3 -m pytest tests/test_check_checks_reported.py::test_queued_check_without_timestamp_blocks_older_pass -q
.                                                                        [100%]
1 passed in 0.22s
```

In-repo guard: `tests/test_check_checks_reported.py::test_reverted_ordering_key_selects_id_1_success_over_queued_pending` encodes the broken ordering without mutating production source.

Gate marker for PR body (if not already present):

```html
<!-- deliberate-break: test=tests/test_check_checks_reported.py::test_queued_check_without_timestamp_blocks_older_pass test-file=tests/test_check_checks_reported.py break-file=scripts/check_checks_reported.py -->
```