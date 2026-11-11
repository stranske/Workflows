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
| [November 11 implementation on matching CPU model](https://github.com/stranske/Workflows/actions/runs/43061809454) | `5a28822cb` | Pass | 6m26s | [4m48s](https://github.com/stranske/Workflows/actions/runs/43061809454/job/130666485333) | 4m09s |

The November 9 baseline predates the grammar partition. The November 11
control provides a closer comparison for the fixture change. The scheduler
trial failed 13 workflow contract tests. The initial fixture trial failed
five tests that validate the original deliberate-break file's hash. The
current implementation keeps that file byte-identical and defines the
fixture in the existing scripts test configuration. The
[PR description](https://github.com/stranske/Workflows/pull/4647) carries
the implementation head's hosted timing receipt, also recorded above.

### Acceptance recheck, November 11

**A2 is met for the observed comparison. A3 is unmet.** Against the
partitioned control, run `43061809454` reduced Gate elapsed by **1m07s**
(14.8%), Python 3.14 job elapsed by **9s** (3.0%), and pytest elapsed by
**11s** (4.2%). Commit `5a28822cb` differs from `f6006fd52` only in this
evidence file. The November 9 issue baseline predates the grammar partition,
so the reductions above use the partitioned control.

The control and faster implementation run both reported AMD EPYC 9V45
CPUs, four xdist workers, and hits for the uv, pytest, and CI artifact caches.
Their Python 3.14 JUnit reports matched all 15,841 testcase identities and
outcomes. Across the 262 deliberate-break cases, aggregate testcase time
fell from 90.9s to 26.6s. The other implementation run used an AMD EPYC
7763 and took 2m22s longer for Gate and 2m54s longer for Python 3.14 than
the control. These observations establish a measured reduction on the
matched pair. The size and repeatability of the overall gain remain uncertain.

Live Actions API readback confirmed that the faster run used
`5a28822cbf1a3c88235f5bc58b0c3dec4561b01b` and
`.github/workflows/pr-00-gate.yml`, with conclusion `success`:

| Measurement | Start (UTC, 2026-11-11) | End (UTC, 2026-11-11) | Elapsed |
| --- | --- | --- | ---: |
| Gate (`created_at` to `updated_at`) | 16:47:42 | 16:54:08 | 6m26s |
| Python 3.14 job | 16:48:26 | 16:53:14 | 4m48s |
| Pytest step | 16:48:51 | 16:53:00 | 4m09s |

The Python 3.14 coverage-minimum step and the
[`summary` job](https://github.com/stranske/Workflows/actions/runs/43061809454/job/130669416968)
both succeeded. The partitioned control's Gate timestamps were 13:54:53
to 14:02:26, and its Python 3.14 job timestamps were 13:55:39 to 14:00:36.

Reproduce the timing readback with the following commands for run IDs
`43061809454` (implementation) and `43033459165` (partitioned control).

```bash
gh api repos/stranske/Workflows/actions/runs/43061809454 \
  --jq '{head_sha,path,status,conclusion,created_at,updated_at,html_url}'
gh api repos/stranske/Workflows/actions/runs/43061809454/jobs --paginate \
  --jq '.jobs[] | select(.name == "python ci / python 3.14" or .name == "summary") | {name,conclusion,started_at,completed_at,steps}'
```

The run IDs above identify the tested revisions for the comparison.

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
