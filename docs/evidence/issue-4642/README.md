# Issue #4642 — Gate python ci / python 3.14 Duration Reduction via pytest-xdist worksteal

## Context & Objectives
Issue #4642 targets the measured `python ci / python 3.14` bottleneck in stranske/Workflows's Gate.
The trailing-7-day Gate p50 needs to be reduced toward 10 min without weakening checks.

The three verifier grammar suites hold ~35.6k parametrized cases and ~38% of the suite's worker time
(Workflows#3904). Running in python-ci, they pushed its pytest step to ~13 minutes. Switching from
loadgroup to worksteal distribution strategy for pytest-xdist dynamically balances test workload
across workers, which is more efficient for heterogeneous test suites with varying test durations.

## Bounded Implementation
Commit 4b9c757f38bcdb07f67fec0357289e1b30e2989b (2026-11-11):
- Adds a new optional `pytest-dist` input parameter to `reusable-10-ci-python.yml` with default value `loadgroup` (backward compatible)
- Updates the pytest command to use the configurable distribution strategy
- Sets `pytest-dist: 'worksteal'` for both `python-ci` and `python-ci-grammar` jobs in `pr-00-gate.yml`
- Documents the new input in `docs/USAGE.md`

## Live Gate Before / After Comparison

Gate elapsed time uses `updatedAt - createdAt` for each run, including queue and setup time.
Job and step durations each use `completedAt - startedAt` at their respective levels.

### Before: Baseline (loadgroup distribution)

| Gate run | Head SHA | Result | Gate interval (UTC) | Gate elapsed | Python 3.14 job | Pytest step | Notes |
| --- | --- | --- | --- | ---: | ---: | ---: | --- |
| TBD | TBD | TBD | TBD | TBD | TBD | TBD | To be populated from historical run before change |

### After: With worksteal distribution

| Gate run | Head SHA | Result | Gate interval (UTC) | Gate elapsed | Python 3.14 job | Pytest step | Notes |
| --- | --- | --- | --- | ---: | ---: | ---: | --- |
| [First PR run](https://github.com/stranske/Workflows/actions/runs/TBD) | `a94a4a47c...` | TBD | TBD | TBD | TBD | TBD | To be populated from first Gate run after merge |

## Health 85 Daily Observations Series

Health 85 is workflow id `387854305` (`Health 85 CI Time Budget`, `.github/workflows/health-85-ci-time-budget.yml`).

| Date | p50 minutes | p50 seconds | Within 600s (10 min) | Health 85 run |
| --- | ---: | ---: | --- | --- |
| 2026-11-04 | TBD | TBD | TBD | TBD |
| 2026-11-05 | TBD | TBD | TBD | TBD |
| 2026-11-06 | TBD | TBD | TBD | TBD |
| 2026-11-07 | TBD | TBD | TBD | TBD |
| 2026-11-08 | TBD | TBD | TBD | TBD |
| 2026-11-09 | TBD | TBD | TBD | TBD |
| 2026-11-10 | TBD | TBD | TBD | TBD |
| 2026-11-11 | TBD | TBD | TBD | TBD |

Acceptance criteria A3: Health 85 reports trailing-seven-day Gate p50 at or below 10 min
for seven consecutive daily measurements.

## Acceptance Criteria Status

- [ ] A1: `pr-00-gate.yml` passes with required checks preserved after the change, verified
  by a completed run of `.github/workflows/pr-00-gate.yml` in which the `python ci / python 3.14`
  test job and all required checks pass; include the run URL in the before/after comparison.
- [ ] A2: The before/after comparison records Gate and `python ci / python 3.14` durations and
  demonstrates a measured reduction.
- [ ] A3: Health 85 reports trailing-seven-day Gate p50 at or below 10 min for seven
  consecutive daily measurements, then closes this issue with the dated p50 series.

## Related Evidence

- Commit: [4b9c757f3](https://github.com/stranske/Workflows/commit/4b9c757f38bcdb07f67fec0357289e1b30e2989b)
- PR: [#4647](https://github.com/stranske/Workflows/pull/4647)
- Source issue: [#4642](https://github.com/stranske/Workflows/issues/4642)
- Related analysis: [issue-3904](docs/evidence/issue-3904/README.md) (verifier grammar suites workload)
