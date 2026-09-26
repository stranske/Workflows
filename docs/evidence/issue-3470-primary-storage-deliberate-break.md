# Deliberate-break evidence: primary-storage refusal (`#3470` / `#3494`)

Relates to merged PR [#3471](https://github.com/stranske/Workflows/pull/3471) and acceptance criteria on [#3470](https://github.com/stranske/Workflows/issues/3470).

Gate test: `tests/scripts/test_runner_lib.py::test_auto_dispatch_requires_primary_storage`

## Baseline (production code)

```text
$ python3 -m pytest tests/scripts/test_runner_lib.py::test_auto_dispatch_requires_primary_storage -q --tb=no
........                                                                 [100%]
8 passed in 6.17s
```

## Deliberate break

In `scripts/runner_lib/core.py`, the auto-dispatch reservation path must write through **primary** storage when `FallbackRunnerStorage` is in use. For the break, that line was temporarily changed to use `storage.fallback` instead (unchecked fallback reservation).

```text
$ python3 -m pytest tests/scripts/test_runner_lib.py::test_auto_dispatch_requires_primary_storage -q --tb=line
...
FAILED ...::test_auto_dispatch_requires_primary_storage[True-True-read]
FAILED ...::test_auto_dispatch_requires_primary_storage[True-True-write]
... (8 failed total)
AssertionError: assert True is False  # should_dispatch must refuse when primary is unavailable
8 failed in 7.93s
```

## Restore

Reverted `reservation_storage` to `storage.primary` for `FallbackRunnerStorage`.

```text
$ python3 -m pytest tests/scripts/test_runner_lib.py::test_auto_dispatch_requires_primary_storage -q --tb=no
........                                                                 [100%]
8 passed in 6.17s
```

<!-- deliberate-break: test=tests/scripts/test_runner_lib.py::test_auto_dispatch_requires_primary_storage command=python3 -m pytest tests/scripts/test_runner_lib.py::test_auto_dispatch_requires_primary_storage -q -->
