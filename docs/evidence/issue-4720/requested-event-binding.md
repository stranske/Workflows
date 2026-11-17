# Issue #4720: requested-event regression proof

The named regression in `tests/test_check_checks_reported.py` now varies only
the recovered workflow run's event across `push`, `pull_request_target`, and
`pull_request`. The workflow supports push and pull-request events, the
head-filtered pull-request search returns no runs, and the same green `gate`
check is present in every case. Suite recovery supplies the run evidence.

With the fixed collector, both wrong-event cases return `UNKNOWN` and name the
missing `pull_request` run for `o/r/.github/workflows/gate.yml`. The recovered
`pull_request` control returns `PASS`. The assertions also verify whether the
recovered run was included in the requested-event inventory.

## Deliberate break and revert

Temporarily restored the original bypass at the start of the
`for job_name, origins in job_provenance.items()` loop in
`scripts/check_checks_reported.py`:

```python
if len(origins) <= 1:
    continue
```

Ran:

```bash
python3 -m pytest tests/test_check_checks_reported.py::test_unique_expected_job_requires_requested_event_run -q -m "not slow"
```

Observed exit code **1**, with these failures:

```text
FAILED tests/test_check_checks_reported.py::test_unique_expected_job_requires_requested_event_run[push]
FAILED tests/test_check_checks_reported.py::test_unique_expected_job_requires_requested_event_run[pull_request_target]
AssertionError: {'verdict': 'PASS', 'expected_names': ['gate'], ...}
assert 'PASS' == 'UNKNOWN'
2 failed, 1 passed in 0.89s
```

The push-only fixture therefore reproduced the incorrect `PASS` while the
requested-event control still passed. Restored the original source bytes in a
`finally` block and verified that `scripts/check_checks_reported.py` had no diff.
Reran the same command after reverting the break:

```text
3 passed in 0.78s
```

Exit code: **0**. The bypass is absent from the final source.

## Full regression file

```bash
python3 -m pytest tests/test_check_checks_reported.py -q -m "not slow"
```

```text
325 passed in 6.91s
```

Exit code: **0**. Existing tests and the bound pull-request run/job/check URL
fixture updates are retained. No existing tests were deleted.

The changed test file passes Black with line length 100, and `git diff --check`
passes.

## Run limitations

The required repository-wide Black command was attempted:

```bash
black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
```

It failed while starting its worker pool because the sandbox refused the
multiprocessing forkserver's socket bind (`PermissionError: Operation not
permitted`). Single-worker and fork-based retries did not finish and were
interrupted. Repository-wide formatting is therefore unverified; the changed
test file's separate formatting check passed.

The sandbox also mounts `.git` read-only. Staging the test change failed with
`Unable to create .../.git/index.lock: Read-only file system`, so this agent
could not create the required commit. Updating the PR body with the verified
checkboxes and proof was refused by the GitHub connector because it requires
approval and this run's approval policy is `never`. The PR body was unchanged.
PR #4729 was confirmed open with `isDraft=false`.

The runner must commit the working-tree test change and this proof, complete the
repository-wide formatting gate, and update the PR acceptance checkboxes.

## Follow-up: no recoverable suite witness

Extended the same named regression with `run_event=None`: both the requested-event
run inventory and the check-suite inventory are empty, while the same green `gate`
check remains present. This case must also emit the exact missing `pull_request`
run diagnostic and retain no identity claims. The three existing event cases and
the bound pull-request fixture remain intact.

Repeated the deliberate break by temporarily restoring the two-line single-origin
bypass at the start of the identity loop, then ran:

```bash
python3 -m pytest tests/test_check_checks_reported.py::test_unique_expected_job_requires_requested_event_run -q -m "not slow"
```

Observed exit **1** with **3 failed, 1 passed in 0.87s**. The `None`, `push`, and
`pull_request_target` cases each failed at the verdict assertion because the
mutated collector returned `PASS` instead of `UNKNOWN`. The recovered
`pull_request` control still passed. The `push` case proves the requested
dual-trigger, push-only false positive.

Restored the collector's original bytes in `finally` and verified that
`git diff -- scripts/check_checks_reported.py` was empty. Repeating the same
named-test command then exited **0** with **4 passed in 0.75s**.

```bash
python3 -m pytest tests/test_check_checks_reported.py -q -m "not slow"
```

Exited **0** with **326 passed in 6.39s**. No existing tests were deleted.
`black --line-length 100 tests/test_check_checks_reported.py`, the changed-file
Black check, `ruff check tests/test_check_checks_reported.py`, and
`git diff --check` also passed.

The repository-wide Black gate again failed with `PermissionError: [Errno 1]
Operation not permitted` when Python's forkserver tried to bind its listener.
A `BLACK_NUM_WORKERS=1` retry produced no result and was interrupted. The mandatory
repository-wide formatting gate therefore remains unverified, so no commit or
push is permitted under this run's pre-commit instructions.
