# Issue #4701 / PR deliberate-break verification

## `test_queued_check_without_timestamp_blocks_older_pass`

### With fix (check_run_is_newer + stamp id tiebreaker)

```
python3 -m pytest tests/test_check_checks_reported.py::test_queued_check_without_timestamp_blocks_older_pass -q
.                                                                        [100%]
1 passed in 1.06s
```

### Deliberate break (revert ordering: stamp-only without id / check_run_is_newer)

Restored pre-fix behavior: `("", 0)` ordering lets older `id=1` success beat newer queued `id=2`.

```
python3 -m pytest tests/test_check_checks_reported.py::test_queued_check_without_timestamp_blocks_older_pass -q
F
AssertionError: assert 'PASS' == 'FAIL'  (verdict PASS returned incorrectly)
1 failed in 0.29s
```

### Full file with fix

```
python3 -m pytest tests/test_check_checks_reported.py -q
300 passed in 7.93s
```