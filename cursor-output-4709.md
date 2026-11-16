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

## November 16 continuation

Commands used `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` with `/opt/anaconda3/bin/python3` because the
environment's auto-loaded pytest-asyncio plugin stopped pytest during configuration.

With the previous pairwise fold, the new three-attempt regression printed:

```text
$ /opt/anaconda3/bin/python3 -m pytest tests/test_check_checks_reported.py::test_three_check_attempts_select_queued_run_in_every_order -q
F.FF.F                                                                   [100%]
4 failed, 2 passed in 0.32s
```

Orders `(1, 2, 3)` and `(2, 1, 3)` selected failed ID 3, raising
`AssertionError: assert 'failure' == 'queued'`. Orders `(2, 3, 1)` and `(3, 2, 1)`
selected successful ID 1, raising `AssertionError: assert 'PASS' == 'FAIL'`.

With deterministic selection, all six permutations returned `FAIL` and selected queued ID 2.
The updated guard also passed by substituting timestamp-only comparison at the final
queued-versus-timestamped selection and observing the false `PASS`.

```text
$ /opt/anaconda3/bin/python3 -m pytest tests/test_check_checks_reported.py::test_three_check_attempts_select_queued_run_in_every_order tests/test_check_checks_reported.py::test_reverted_ordering_key_selects_id_1_success_over_queued_pending -q
.......                                                                  [100%]
7 passed in 0.24s
$ /opt/anaconda3/bin/python3 -m pytest tests/test_check_checks_reported.py -q
311 passed in 5.18s
```

Temporarily replacing the final comparison with timestamp-only ordering in production source
also broke the original named regression. Restoring the source byte for byte made it pass:

```text
$ /opt/anaconda3/bin/python3 -m pytest tests/test_check_checks_reported.py::test_queued_check_without_timestamp_blocks_older_pass -q
E           AssertionError: assert 'PASS' == 'FAIL'
1 failed in 0.19s
Restored production source byte for byte
$ /opt/anaconda3/bin/python3 -m pytest tests/test_check_checks_reported.py::test_queued_check_without_timestamp_blocks_older_pass -q
.                                                                        [100%]
1 passed in 0.16s
```
