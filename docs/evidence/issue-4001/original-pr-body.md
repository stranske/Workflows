## Summary
- add discriminating metric aggregation boundary coverage
- exercise consumer drift CLI, remote-read, and report rendering failure paths
- validate document identity and artifact-path contract guards

## Coverage
Focused baseline -> after: `aggregate_agent_metrics.py` 98.12% -> 99.53%; `check_consumer_sync_drift.py` 84.09% -> 90.33%; `validate_run_contract.py` 85.76% -> 88.33%. The issue snapshot (82.29% whole-repo CI) differs from focused local coverage; CI remains the authoritative gate.

## Break-and-revert proof
- `aggregate_agent_metrics.py`: deliberately returned `unknown` for a recognized patterned artifact; `pytest tests/scripts/test_aggregate_agent_metrics.py -q` failed; reverted and passed.
- `check_consumer_sync_drift.py`: deliberately changed the highest-impact report heading; `pytest tests/scripts/test_check_consumer_sync_drift.py -q` failed; reverted and passed.
- `validate_run_contract.py`: deliberately inverted the identical-hash supersession guard; `pytest tests/contracts/test_validate_run_contract.py -q` failed; reverted and passed.

## Validation
- `/opt/anaconda3/bin/python3 -m pytest tests/scripts/test_aggregate_agent_metrics.py tests/scripts/test_check_consumer_sync_drift.py tests/contracts/test_validate_run_contract.py tests/scripts/test_validate_run_contract.py --cov=scripts.aggregate_agent_metrics --cov=scripts.check_consumer_sync_drift --cov=scripts.validate_run_contract --cov-report=term -q` (234 passed)
- `black --check --line-length 100` on changed tests (passed)
- `ruff check` on changed tests (passed)

Closes #4001

<!-- pr-preamble:start -->
<!-- meta:issue:4001 -->
> **Source:** Issue #4001

Closes #4001

<!-- pr-preamble:end -->

<!-- auto-status-summary:start -->
## Automated Status Summary
#### Scope
Workflows reads 82.29% blended line+branch in CI; reaching 90% needs about 4488 more covered statements+branches. Prioritize fleet's largest gap by far.

The target order below is the Orchestrator's own ranking (escaped defects, then churn, then uncovered mass -- unchanged). Only the bundling is new: earlier rounds spent a whole PR on files with a handful of uncovered statements, so one PR now covers the next ranked targets until it has covered about 180 units.

<!-- Updated WORKFLOW_OUTPUTS.md context:start -->
## Context for Agent

### Related Issues/PRs
- [#3962](https://github.com/stranske/Workflows/issues/3962)
- [#3965](https://github.com/stranske/Workflows/issues/3965)
<!-- Updated WORKFLOW_OUTPUTS.md context:end -->

#### Tasks
- [ ] "Uncovered units" here come from the repository's whole CI run (every test file together). One test module's own suite can already cover more than CI's count shows for that module, and CI's figure is the one this PR is judged on: if your baseline differs, say so in the PR body and use CI's number.
- [ ] Before you push, run the repository's own formatter and linter on every file you add or change, with the flags its CI `lint-format` and `lint-ruff` jobs use: one unformatted file fails a required check, and waiting for the autofix bot to repair it afterwards has not worked on lane PRs.
- [ ] This repository's CI runs `black --check --line-length 100` and `ruff check` over the whole tree (the required `lint-format` job): run `black --line-length 100` on every file you add or change before you push. Two of the first three lane PRs here (#3962 and #3965) failed that job on one new test file each, and the autofix bot escalated instead of repairing them.

#### Acceptance criteria
- [ ] `pytest` passes in CI with the new tests, and each new test fails when the code it covers is deliberately broken (the PR body shows the break-and-revert run).
- [ ] The PR's Gate coverage shows the targets' uncovered statements+branches down by about 180 or more, or the PR body explains each target that could not be meaningfully covered.
- [ ] Production code changes only where a test found a real bug, each one explained in the PR body.

- [ ] Same contract as every round in this initiative:
1. [ ] Pick the next target by the repo's own coverage-gap ranking (escaped-defect priority, then
   churn, then uncovered mass), not by file size.
2. [ ] Every new test must FAIL when the code it covers is deliberately broken and PASS when
   reverted -- run that break-and-revert for real and report it, don't assert it.
3. [ ] Real bugs found while writing tests get fixed with a minimal, targeted diff in the same PR,
   not worked around. Watch for the negative-cache pattern (cache.get(key) is None used as a 'not yet cached' check, which can't tell 'never queried' from 'queried and got nothing') -- it has recurred independently four separate times fleet-wide already.
4. [ ] Low blast radius only -- test-only or tightly-scoped fixes, no refactors.
5. [ ] One PR per logical chunk of work.

- [ ] The goal is to improve the code, not a metric. If you measure this repo at or above 90% before
- [ ] starting, say so in a comment on this issue and close it without opening a PR -- do not
- [ ] manufacture a fix just because a round was requested.

**Head SHA:** f7c27207cd2e7c06f3cc3c45e651957b0b4c8962
**Latest Runs:** ✅ success — Gate
**Required:** gate: ✅ success

| Workflow / Job | Result | Logs |
|----------------|--------|------|
| Backplane Contract Integrity | ✅ success | [View run](https://github.com/stranske/Workflows/actions/runs/39009963661) |
| Gate | ✅ success | [View run](https://github.com/stranske/Workflows/actions/runs/39009963668) |
| Health 40 Sweep | ✅ success | [View run](https://github.com/stranske/Workflows/actions/runs/39009963695) |
| Health 44 Gate Branch Protection | ✅ success | [View run](https://github.com/stranske/Workflows/actions/runs/39009963665) |
| Health 45 Agents Guard | ✅ success | [View run](https://github.com/stranske/Workflows/actions/runs/39009963703) |
| Health 50 Security Scan | ✅ success | [View run](https://github.com/stranske/Workflows/actions/runs/39009963659) |
| Health 52 Semgrep Scan | ✅ success | [View run](https://github.com/stranske/Workflows/actions/runs/39009963666) |
| Health 74 Template Drift | ✅ success | [View run](https://github.com/stranske/Workflows/actions/runs/39009960536) |
| Maint 52 Validate Workflows | ✅ success | [View run](https://github.com/stranske/Workflows/actions/runs/39009963677) |
| PR 11 - Minimal invariant CI | ✅ success | [View run](https://github.com/stranske/Workflows/actions/runs/39009963667) |
| PR 46 Dependency Repair Contract | ⏭️ skipped | Last completed result; current run in PR checks |
| Selftest CI | ✅ success | [View run](https://github.com/stranske/Workflows/actions/runs/39009963712) |
<!-- auto-status-summary:end -->
