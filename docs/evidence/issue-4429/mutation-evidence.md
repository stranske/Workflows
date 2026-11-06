Mutation checks run in `/tmp/issue-4429/probe`, an isolated copy of the target modules and test modules. The baseline suite in the working checkout never sees a mutation. Each command includes `-m "not slow"`. The validator check is an existing test, rerun to retain full validator evidence.

### `tests/scripts/test_check_consumer_sync_drift.py::test_main_caches_a_blob_miss_but_reads_other_shas_and_retries_next_run`

Temporary change in `scripts/check_consumer_sync_drift.py`:

```diff
-        if key not in blob_text_cache:
+        if blob_text_cache.get(key) is None:
```

RED

```text
$ /opt/hostedtoolcache/Python/3.14.10/x64/bin/python -m pytest tests/scripts/test_check_consumer_sync_drift.py::test_main_caches_a_blob_miss_but_reads_other_shas_and_retries_next_run -m "not slow" -q --tb=short
F                                                                        [100%]
=================================== FAILURES ===================================
____ test_main_caches_a_blob_miss_but_reads_other_shas_and_retries_next_run ____
tests/scripts/test_check_consumer_sync_drift.py:684: in test_main_caches_a_blob_miss_but_reads_other_shas_and_retries_next_run
    assert report["drift"] == ["owner/repo: managed/a.txt", "owner/repo: managed/b.txt"]
E   AssertionError: assert ['owner/repo: managed/a.txt'] == ['owner/repo:...anaged/b.txt']
E
E     Right contains one more item: 'owner/repo: managed/b.txt'
E
E     Full diff: (-: missing in left side, +: extra in left side)
E       [
E           'owner/repo: managed/a.txt',
E     -     'owner/repo: managed/b.txt',
E       ]
----------------------------- Captured stdout call -----------------------------
::warning::Consumer repo drift detected
=========================== short test summary info ============================
FAILED tests/scripts/test_check_consumer_sync_drift.py::test_main_caches_a_blob_miss_but_reads_other_shas_and_retries_next_run - AssertionError: assert ['owner/repo: managed/a.txt'] == ['owner/repo:...anaged/b.txt']

  Right contains one more item: 'owner/repo: managed/b.txt'

  Full diff: (-: missing in left side, +: extra in left side)
    [
        'owner/repo: managed/a.txt',
  -     'owner/repo: managed/b.txt',
    ]
1 failed in 0.92s
exit=1
```

Reverted the temporary change byte-for-byte; restored SHA-256 `ef01bfd16273d6901cadc6acca71f07485cd1fb7b1bb07bc31b1b6dbddfc060e`.

GREEN

```text
$ /opt/hostedtoolcache/Python/3.14.10/x64/bin/python -m pytest tests/scripts/test_check_consumer_sync_drift.py::test_main_caches_a_blob_miss_but_reads_other_shas_and_retries_next_run -m "not slow" -q --tb=short
.                                                                        [100%]
1 passed in 0.69s
exit=0
```

### `tests/scripts/test_aggregate_agent_metrics.py::test_trace_refs_ignore_empty_items_without_losing_later_refs`

Temporary change in `scripts/aggregate_agent_metrics.py`:

```diff
-            elif item_trace_url:
+            else:
```

RED

```text
$ /opt/hostedtoolcache/Python/3.14.10/x64/bin/python -m pytest tests/scripts/test_aggregate_agent_metrics.py::test_trace_refs_ignore_empty_items_without_losing_later_refs -m "not slow" -q --tb=short
F                                                                        [100%]
=================================== FAILURES ===================================
_________ test_trace_refs_ignore_empty_items_without_losing_later_refs _________
tests/scripts/test_aggregate_agent_metrics.py:488: in test_trace_refs_ignore_empty_items_without_losing_later_refs
    assert aggregate_agent_metrics._langsmith_trace_refs(
E   AssertionError: assert {'id:later', 'url:'} == {'id:later'}
E
E     Extra items in the left set:
E     'url:'
E
E     Full diff: (-: missing in left side, +: extra in left side)
E       {
E           'id:later',
E     +     'url:',
E       }
=========================== short test summary info ============================
FAILED tests/scripts/test_aggregate_agent_metrics.py::test_trace_refs_ignore_empty_items_without_losing_later_refs - AssertionError: assert {'id:later', 'url:'} == {'id:later'}

  Extra items in the left set:
  'url:'

  Full diff: (-: missing in left side, +: extra in left side)
    {
        'id:later',
  +     'url:',
    }
1 failed in 0.91s
exit=1
```

Reverted the temporary change byte-for-byte; restored SHA-256 `e03bd53293d5627de350405f9dcfdda966b9071c7954c59241ced4cbf12bd1df`.

GREEN

```text
$ /opt/hostedtoolcache/Python/3.14.10/x64/bin/python -m pytest tests/scripts/test_aggregate_agent_metrics.py::test_trace_refs_ignore_empty_items_without_losing_later_refs -m "not slow" -q --tb=short
.                                                                        [100%]
1 passed in 0.67s
exit=0
```

### `tests/scripts/test_aggregate_agent_metrics.py::test_autopilot_unknown_success_keeps_duration_without_counting_an_outcome`

Temporary change in `scripts/aggregate_agent_metrics.py`:

```diff
-        elif success in (False, "false", "False", "0", 0):
+        else:
```

RED

```text
$ /opt/hostedtoolcache/Python/3.14.10/x64/bin/python -m pytest tests/scripts/test_aggregate_agent_metrics.py::test_autopilot_unknown_success_keeps_duration_without_counting_an_outcome -m "not slow" -q --tb=short
F                                                                        [100%]
=================================== FAILURES ===================================
__ test_autopilot_unknown_success_keeps_duration_without_counting_an_outcome ___
tests/scripts/test_aggregate_agent_metrics.py:509: in test_autopilot_unknown_success_keeps_duration_without_counting_an_outcome
    assert summary["total_steps"] == 1
E   assert 3 == 1
=========================== short test summary info ============================
FAILED tests/scripts/test_aggregate_agent_metrics.py::test_autopilot_unknown_success_keeps_duration_without_counting_an_outcome - assert 3 == 1
1 failed in 0.76s
exit=1
```

Reverted the temporary change byte-for-byte; restored SHA-256 `e03bd53293d5627de350405f9dcfdda966b9071c7954c59241ced4cbf12bd1df`.

GREEN

```text
$ /opt/hostedtoolcache/Python/3.14.10/x64/bin/python -m pytest tests/scripts/test_aggregate_agent_metrics.py::test_autopilot_unknown_success_keeps_duration_without_counting_an_outcome -m "not slow" -q --tb=short
.                                                                        [100%]
1 passed in 0.67s
exit=0
```

### `tests/scripts/test_aggregate_agent_metrics.py::test_freshness_ignores_blank_target_paths_without_losing_later_targets`

Temporary change in `scripts/aggregate_agent_metrics.py`:

```diff
-                if path:
                    update_targets[path] += 1
+                if isinstance(path, str):
                    update_targets[path] += 1
```

RED

```text
$ /opt/hostedtoolcache/Python/3.14.10/x64/bin/python -m pytest tests/scripts/test_aggregate_agent_metrics.py::test_freshness_ignores_blank_target_paths_without_losing_later_targets -m "not slow" -q --tb=short
F                                                                        [100%]
=================================== FAILURES ===================================
____ test_freshness_ignores_blank_target_paths_without_losing_later_targets ____
tests/scripts/test_aggregate_agent_metrics.py:532: in test_freshness_ignores_blank_target_paths_without_losing_later_targets
    assert summary["update_targets"] == Counter({"config/versions.env": 2})
E   AssertionError: assert Counter({'': ...ions.env': 2}) == Counter({'con...ions.env': 2})
E
E     Omitting 1 identical items, use -vv to show
E     Left contains 1 more item:
E     {'': 2}
E
E     Full diff: (-: missing in left side, +: extra in left side)
E       Counter({
E     +     '': 2,
E           'config/versions.env': 2,
E       })
=========================== short test summary info ============================
FAILED tests/scripts/test_aggregate_agent_metrics.py::test_freshness_ignores_blank_target_paths_without_losing_later_targets - AssertionError: assert Counter({'': ...ions.env': 2}) == Counter({'con...ions.env': 2})

  Omitting 1 identical items, use -vv to show
  Left contains 1 more item:
  {'': 2}

  Full diff: (-: missing in left side, +: extra in left side)
    Counter({
  +     '': 2,
        'config/versions.env': 2,
    })
1 failed in 1.11s
exit=1
```

Reverted the temporary change byte-for-byte; restored SHA-256 `e03bd53293d5627de350405f9dcfdda966b9071c7954c59241ced4cbf12bd1df`.

GREEN

```text
$ /opt/hostedtoolcache/Python/3.14.10/x64/bin/python -m pytest tests/scripts/test_aggregate_agent_metrics.py::test_freshness_ignores_blank_target_paths_without_losing_later_targets -m "not slow" -q --tb=short
.                                                                        [100%]
1 passed in 1.09s
exit=0
```

### `tests/scripts/test_validate_run_contract.py::test_document_page_checks_reject_conflicts_and_noncanonical_dates`

Temporary change in `scripts/validate_run_contract.py`:

```diff
-def _check_document_page(document: Any, report: Report, prefix: str = "") -> None:
+def _check_document_page(document: Any, report: Report, prefix: str = "") -> None:
    return
```

RED

```text
$ /opt/hostedtoolcache/Python/3.14.10/x64/bin/python -m pytest tests/scripts/test_validate_run_contract.py::test_document_page_checks_reject_conflicts_and_noncanonical_dates -m "not slow" -q --tb=short
F                                                                        [100%]
=================================== FAILURES ===================================
______ test_document_page_checks_reject_conflicts_and_noncanonical_dates _______
tests/scripts/test_validate_run_contract.py:65: in test_document_page_checks_reject_conflicts_and_noncanonical_dates
    assert not report.conformant
E   AssertionError: assert not True
E    +  where True = Report(repo='owner/repo', role='', conformant=True, skipped=False, violations=[]).conformant
=========================== short test summary info ============================
FAILED tests/scripts/test_validate_run_contract.py::test_document_page_checks_reject_conflicts_and_noncanonical_dates - AssertionError: assert not True
 +  where True = Report(repo='owner/repo', role='', conformant=True, skipped=False, violations=[]).conformant
1 failed in 0.74s
exit=1
```

Reverted the temporary change byte-for-byte; restored SHA-256 `5b769c2ea3d9edb526b0ffd706e9611cf7b086140c65bae639f5b58088e36efa`.

GREEN

```text
$ /opt/hostedtoolcache/Python/3.14.10/x64/bin/python -m pytest tests/scripts/test_validate_run_contract.py::test_document_page_checks_reject_conflicts_and_noncanonical_dates -m "not slow" -q --tb=short
.                                                                        [100%]
1 passed in 0.69s
exit=0
```
