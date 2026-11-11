# Workflows #4642 Gate timing evidence

The linked November 9 Gate run spent 13m19s of the 14m02s Python 3.14
job in pytest. Its JUnit report attributed 650.4 aggregate testcase seconds
to the verifier delivery-destination suite and 167.4 seconds to
`tests/scripts/test_check_deliberate_break.py`. The verifier grammar
partition from [Workflows #3904](../issue-3904/README.md) is already on main.
On the passing November 11 partitioned control, the deliberate-break file
was the largest remaining file by aggregate testcase duration at 90.9 seconds.

The deliberate-break file builds synthetic repositories and launches real
pytest subprocesses for head and base. A fixture in `tests/scripts/conftest.py`
disables third-party entry-point plugin autoload in those child processes
when the file runs on an xdist worker. Pytest's built-in plugins, the
synthetic repositories' conftests, and the existing verdict assertions still
run. The archived serial comparison retains its plugin environment and the
test file retains its original hash. Both Gate partitions retain the existing
scheduler, test selection, Python matrix, and coverage settings.

## Gate measurements

Gate elapsed is the Actions run `updated_at - created_at`. Job and pytest
elapsed are their respective `completed_at - started_at`. Aggregate JUnit
testcase seconds can overlap across workers.

| Run | Head | Result | Gate | Python 3.14 job | Pytest step |
| --- | --- | --- | ---: | ---: | ---: |
| [November 9 issue baseline](https://github.com/stranske/Workflows/actions/runs/42538564663) | `c3eed332a` | Pass | 27m16s | [14m02s](https://github.com/stranske/Workflows/actions/runs/42538564663/job/128910700729) | 13m19s |
| [November 11 partitioned control](https://github.com/stranske/Workflows/actions/runs/43033459165) | `0aad55c39` | Pass | 7m33s | [4m57s](https://github.com/stranske/Workflows/actions/runs/43033459165/job/130566504739) | 4m20s |
| [November 11 scheduler trial](https://github.com/stranske/Workflows/actions/runs/43049167125) | `0a4e9dbaf` | Fail | 13m38s | [5m10s](https://github.com/stranske/Workflows/actions/runs/43049167125/job/130624948089) | 4m28s |
| [November 11 fixture trial](https://github.com/stranske/Workflows/actions/runs/43057239997) | `8602e65ed` | Fail | 7m25s | [5m49s](https://github.com/stranske/Workflows/actions/runs/43057239997/job/130650270755) | 5m14s |

The November 9 baseline predates the grammar partition. The November 11
control provides a closer comparison for the fixture change. The scheduler
trial failed 13 workflow contract tests. The initial fixture trial failed
five tests that validate the original deliberate-break file's hash. The
current implementation keeps that file byte-identical and defines the
fixture in the existing scripts test configuration. The
[PR description](https://github.com/stranske/Workflows/pull/4647) carries
the final head's hosted timing receipt.

## Focused validation on November 11

The same 262 cases passed in 26.82s without the fixture and 10.16s with the
scoped fixture, using four local xdist workers.

```bash
/opt/anaconda3/bin/python3 -m pytest -q -o asyncio_default_fixture_loop_scope=function \
  -n 4 --dist=loadgroup -m 'not quarantine and not slow' --durations=5 \
  tests/scripts/test_check_deliberate_break.py
```

The focused Gate scheduling and coverage contracts passed 30 cases in 3.21s.
The target module plus both archive-binding test files passed 290 cases
in 12.79s with the relocated fixture.

## Health 85

Health 85 measures the trailing-seven-day median of each Gate run's longest
executed job. Source issue [#4642](https://github.com/stranske/Workflows/issues/4642)
requires seven consecutive daily readings at or below 10 minutes and closure
by Health 85.

| Observation date (UTC) | Gate p50 | Health 85 run |
| --- | ---: | --- |
| 2026-11-10 | 11m08s | [42838942059](https://github.com/stranske/Workflows/actions/runs/42838942059) |
| 2026-11-11 | 10m30s | [43013607206](https://github.com/stranske/Workflows/actions/runs/43013607206) |
