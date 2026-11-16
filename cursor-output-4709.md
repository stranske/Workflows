## Deliberate break → revert (acceptance criterion 2)

Reverted the ordering key in `check_run_is_newer` at `scripts/check_checks_reported.py` (~1292) to stamp-only comparison `(timestamp or "", id)` with no timestampless queued handling—the pre-fix behavior.

### Broken head (`check_run_is_newer` reverted)

```text
$ python3 -m pytest tests/test_check_checks_reported.py::test_queued_check_without_timestamp_blocks_older_pass -q
FAILED ... AssertionError: assert 'PASS' == 'FAIL'
  - FAIL
  + PASS
1 failed
```

Observed: id=1 completed success selected, overall verdict `PASS` (regression).

### Restored fix

```text
$ python3 -m pytest tests/test_check_checks_reported.py::test_queued_check_without_timestamp_blocks_older_pass -q
.                                                                        [100%]
1 passed
```

In-repo guard: `tests/test_check_checks_reported.py::test_reverted_ordering_key_selects_id_1_success_over_queued_pending` encodes the broken ordering without mutating production source.

Gate marker for PR body (if not already present):

```html
<!-- deliberate-break: test=tests/test_check_checks_reported.py::test_queued_check_without_timestamp_blocks_older_pass test-file=tests/test_check_checks_reported.py break-file=scripts/check_checks_reported.py -->
```