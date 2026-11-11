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
| [November 11 completed implementation](https://github.com/stranske/Workflows/actions/runs/43058643708) | `f6006fd52` | Pass | 9m55s | [7m51s](https://github.com/stranske/Workflows/actions/runs/43058643708/job/130655297466) | 7m06s |

The November 9 baseline predates the grammar partition. The November 11
control provides a closer comparison for the fixture change. The scheduler
trial failed 13 workflow contract tests. The initial fixture trial failed
five tests that validate the original deliberate-break file's hash. The
current implementation keeps that file byte-identical and defines the
fixture in the existing scripts test configuration. The
[PR description](https://github.com/stranske/Workflows/pull/4647) carries
the implementation head's hosted timing receipt, also recorded above.

### Acceptance recheck, November 11 (keepalive round 9)

Outcome: **A2 remains unverified for this PR's change; A3 is unmet.**
The implementation run is 17m21s (63.6%) shorter for Gate and 6m11s
(44.1%) shorter for Python 3.14 than the issue's November 9 baseline.
However, that baseline predates the grammar partition already on main.
Against the partitioned control, this PR's implementation run is **2m22s
longer for Gate and 2m54s longer for Python 3.14**. The earlier local
test-file speedup therefore does not establish a hosted Gate/job speedup
attributable to this change. Keep A2 unchecked pending such evidence.

Live Actions API readback confirmed the completed implementation run used
`f6006fd521907733694542fd980e45f1e5018aa4` and
`.github/workflows/pr-00-gate.yml`, with conclusion `success`:

| Measurement | Start (UTC, 2026-11-11) | End (UTC, 2026-11-11) | Elapsed |
| --- | --- | --- | ---: |
| Gate (`created_at` to `updated_at`) | 16:28:17 | 16:38:12 | 9m55s |
| Python 3.14 job | 16:29:06 | 16:36:57 | 7m51s |
| Pytest step | 16:29:38 | 16:36:44 | 7m06s |

The Python 3.14 coverage-minimum step and the
[`summary` job](https://github.com/stranske/Workflows/actions/runs/43058643708/job/130660144605)
both succeeded. The partitioned control's Gate timestamps were 13:54:53
to 14:02:26, and its Python 3.14 job timestamps were 13:55:39 to 14:00:36.
These are single-run observations, not a controlled estimate of causality.

Reproduce the timing readback with the following commands for run IDs
`43058643708` (implementation) and `43033459165` (partitioned control):

```bash
gh api repos/stranske/Workflows/actions/runs/43058643708 \
  --jq '{head_sha,path,status,conclusion,created_at,updated_at,html_url}'
gh api repos/stranske/Workflows/actions/runs/43058643708/jobs --paginate \
  --jq '.jobs[] | select(.name == "python ci / python 3.14" or .name == "summary") | {name,conclusion,started_at,completed_at,steps}'
```

This round changes evidence only. It neither changes validation nor claims
that the implementation run tested this subsequent documentation commit.

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

Live readback of the [published report](https://github.com/stranske/Workflows/blob/ci-time-budget/docs/reports/ci-budget.json)
at blob `4ab19f353c1821833026bdfc11f04630ae60b097` confirmed the
Workflows entry was measured at `2026-11-11T11:38:35+00:00`, with 754
samples and p50 10.5 minutes. Its dated series contains null observations
for November 5, 6, and 7, followed by the two over-target readings above.
There is no qualifying seven-day series, and source issue #4642 is open.
Health 85 owns the daily measurement and eventual closure; a same-day
rerun cannot substitute for seven consecutive daily measurements.
