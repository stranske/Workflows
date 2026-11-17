# Issue #4720: unique expected-job event binding

The named regression uses a workflow triggered by both `push` and
`pull_request`. Its push-only case has zero pull-request runs and a green
exact-head check bound to the push run's suite. The test also verifies that jobs
from a different event are excluded and that the gap names the missing
`pull_request` run. The pull-request case is the positive control.

## Deliberate break

Temporarily restored this bypass at the start of the `job_provenance` loop in
`scripts/check_checks_reported.py`:

```python
if len(origins) <= 1:
    continue
```

Ran:

```bash
python3 -m pytest 'tests/test_check_checks_reported.py::test_unique_expected_job_requires_requested_event_run[push]' -q -m "not slow" --tb=short
```

Exit status: **1**. The collector incorrectly returned `PASS`; the named
regression failed with `assert 'PASS' == 'UNKNOWN'`:

```text
F                                                                        [100%]
=================================== FAILURES ===================================
_________ test_unique_expected_job_requires_requested_event_run[push] __________
tests/test_check_checks_reported.py:650: in test_unique_expected_job_requires_requested_event_run
    assert result["verdict"] == "UNKNOWN", result
E   AssertionError: {'verdict': 'PASS', 'expected_names': ['gate'], 'reported_names': ['gate'], 'passing_names': ['gate'], ...}
E   assert 'PASS' == 'UNKNOWN'
E     
E     - UNKNOWN
E     + PASS
=========================== short test summary info ============================
FAILED tests/test_check_checks_reported.py::test_unique_expected_job_requires_requested_event_run[push] - AssertionError: {'verdict': 'PASS', 'expected_names': ['gate'], 'reported_names': ['gate'], 'passing_names': ['gate'], ...}
assert 'PASS' == 'UNKNOWN'
  
  - UNKNOWN
  + PASS
1 failed in 0.86s
```

## Revert and verification

Restored `scripts/check_checks_reported.py` byte for byte before rerunning:

```bash
python3 -m pytest tests/test_check_checks_reported.py::test_unique_expected_job_requires_requested_event_run -q -m "not slow"
```

Exit status: **0**, **4 passed**. Missing and wrong-event run witnesses produce
`UNKNOWN` with an explicit missing `pull_request` run gap. The matching-event
positive control produces `PASS`.

```bash
python3 -m pytest tests/test_check_checks_reported.py -q -m "not slow"
```

Exit status: **0**, **326 passed**. Existing tests were retained.

## Formatting and lint

Formatted the changed test with `black --line-length 100
 tests/test_check_checks_reported.py` (one file unchanged).
`ruff check tests/test_check_checks_reported.py` passed.

The required repository-wide Black CLI options were checked through the same
CLI entry point, with only its worker dispatch replaced by sequential calls.
The default process pool was unavailable in the sandbox, and the single-worker
thread fallback stalled awaiting result notifications. File discovery,
exclusions, formatting, caching and reporting were preserved:

```python
import black
import black.concurrency


def sequential_reformat_many(
    sources, fast, write_back, mode, report, workers, no_cache=False, cache_dir=None
):
    for source in sorted(sources):
        black.reformat_one(
            source, fast, write_back, mode, report,
            no_cache=no_cache, cache_dir=cache_dir,
        )


black.concurrency.reformat_many = sequential_reformat_many
black.main([
    "--check", "--line-length", "100",
    "--exclude", r"(\.workflows-lib|node_modules)", ".",
])
```

Exit status: **0**, **1,021 files would be left unchanged**.

## Current run verification (2026-11-17)

Reviewed commits `08772106` through `c3d45159`: the source bypass is removed,
the shared fixture supplies a bound pull-request run/job/check URL, and existing
tests remain present. Added two cases to
`test_unique_expected_job_requires_source_job_and_check_binding`: the bound
check is queued or failed while a newer same-name check at another URL succeeds.
Both cases require `UNKNOWN` and a check-URL binding diagnostic despite
`passing_names == ["gate"]`.

Temporarily restored the two-line bypass in the collector's identity loop and ran:

```bash
python3 -m pytest tests/test_check_checks_reported.py::test_unique_expected_job_requires_requested_event_run -q -m "not slow" --tb=short
```

Exit **1**, **4 failed in 1.14s**. The push-only case failed with:

```text
_________ test_unique_expected_job_requires_requested_event_run[push] __________
tests/test_check_checks_reported.py:650: in test_unique_expected_job_requires_requested_event_run
    assert result["verdict"] == "UNKNOWN", result
E   assert 'PASS' == 'UNKNOWN'
```

The missing-run and `pull_request_target` cases likewise returned `PASS`.
The pull-request control failed because the bypass removed its identity claim.
Restored the original collector bytes in `finally` and verified no source diff.

After restoring:

```bash
python3 -m pytest tests/test_check_checks_reported.py::test_unique_expected_job_requires_requested_event_run -q -m "not slow"
# 4 passed in 0.84s; exit 0
python3 -m pytest tests/test_check_checks_reported.py -q -m "not slow"
# 328 passed in 8.75s; exit 0
```

The changed-file Black check, Ruff, and `git diff --check` pass. The required
repository-wide command
`black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .`
exited **1**: Python's multiprocessing forkserver could not bind its listener
(`PermissionError: [Errno 1] Operation not permitted`). The mandatory formatting
gate therefore blocks committing. Independently, `findmnt -T .git` confirms
that `.git` is mounted read-only. No commit or push was made.

GitHub reports PR #4729 as **merged**, closed at `2026-11-17T06:22:29Z`, with
`draft=false`. Its named-test and break/revert acceptance boxes remain unchecked.
The attempt to reconcile the verified named-test checkbox was rejected with
`MCP tool call requires approval, but approval policy is never`; the PR body
was unchanged. These results are local evidence for the runner to publish.
