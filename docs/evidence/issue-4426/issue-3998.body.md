<!-- coverage-autopilot:chunk-round -->
Continuing the fleet coverage initiative -- lane D: ONE chunk, ONE PR. Opened automatically by coverage-autopilot.py; the next chunk opens when this round closes.

Claimed: coverage-autopilot.py dispatches an agent on this issue as soon as it opens, and that agent opens ONE pull request. Lanes, please skip this issue so two writers do not collide. The claim expires on its own: if no pull request is linked to this issue by 2026-10-17T07:44:10Z, treat it as released.

## Why

Workflows reads 82.29% blended line+branch in CI; reaching 90% needs about 4488 more covered statements+branches. Prioritize fleet's largest gap by far.

The target order below is the Orchestrator's own ranking (escaped defects, then churn, then uncovered mass -- unchanged). Only the bundling is new: earlier rounds spent a whole PR on files with a handful of uncovered statements, so one PR now covers the next ranked targets until it has covered about 180 units.

## Scope

Targets, in this order (about 398 uncovered statements+branches in all):

1. `scripts/sync_test_dependencies.py` -- 6 uncovered statements+branches (15 escaped-defect signal(s), churn 16, fix commit touched this file)
2. `scripts/langchain/issue_pr_context.py` -- 30 uncovered statements+branches (7 escaped-defect signal(s), churn 9, fix commit touched this file)
3. `scripts/langchain/verifier_config.py` -- 16 uncovered statements+branches (6 escaped-defect signal(s), churn 8, fix commit touched this file)
4. `tools/langchain_client.py` -- 29 uncovered statements+branches (6 escaped-defect signal(s), churn 7, fix commit touched this file)
5. `scripts/langchain/task_validator.py` -- 36 uncovered statements+branches (5 escaped-defect signal(s), churn 8, fix commit touched this file)
6. `scripts/langchain/pr_verifier.py` -- 281 uncovered statements+branches (4 escaped-defect signal(s), churn 8, fix commit touched this file)

Cover as many of these as you can cover FULLY in this one PR, in order, with discriminating tests; stop when about 180 units are covered or the list is exhausted. Touch only tests, plus a minimal production fix when a test finds a real bug. Other lanes own other files; do not touch these (in flight or reserved): `scripts/aggregate_agent_metrics.py`, `scripts/check_consumer_sync_drift.py`, `scripts/langchain/followup_issue_generator.py`, `scripts/runner_lib/core.py`.

## Implementation Notes

- "Uncovered units" here come from the repository's whole CI run (every test file together). One test module's own suite can already cover more than CI's count shows for that module, and CI's figure is the one this PR is judged on: if your baseline differs, say so in the PR body and use CI's number.
- Before you push, run the repository's own formatter and linter on every file you add or change, with the flags its CI `lint-format` and `lint-ruff` jobs use: one unformatted file fails a required check, and waiting for the autofix bot to repair it afterwards has not worked on lane PRs.
- This repository's CI runs `black --check --line-length 100` and `ruff check` over the whole tree (the required `lint-format` job): run `black --line-length 100` on every file you add or change before you push. Two of the first three lane PRs here (#3962 and #3965) failed that job on one new test file each, and the autofix bot escalated instead of repairing them.

## Non-Goals

No refactors, no exclusions or threshold changes, no files outside the targets, no padding: if a listed target cannot be meaningfully tested (dead code, an external service you cannot fake), say so in the PR body and take the next one.

## Tasks

- [ ] Cover `scripts/sync_test_dependencies.py` (6 uncovered statements+branches): write tests under `tests/` for its untested lines and branches.
- [ ] Cover `scripts/langchain/issue_pr_context.py` (30 uncovered statements+branches): write tests under `tests/` for its untested lines and branches.
- [ ] Cover `scripts/langchain/verifier_config.py` (16 uncovered statements+branches): write tests under `tests/` for its untested lines and branches.
- [ ] Cover `tools/langchain_client.py` (29 uncovered statements+branches): write tests under `tests/` for its untested lines and branches.
- [ ] Cover `scripts/langchain/task_validator.py` (36 uncovered statements+branches): write tests under `tests/` for its untested lines and branches.
- [ ] Cover `scripts/langchain/pr_verifier.py` (281 uncovered statements+branches): write tests under `tests/` for its untested lines and branches.
- [ ] For each new test, run the break-and-revert proof (break the code it covers, `pytest` fails; revert, `pytest` passes) and record both results in the PR body.
- [ ] If a test exposes a real bug in a target above, fix it with the smallest diff and show `pytest tests/` green again.
- [ ] Open ONE PR whose body states each target's coverage before and after (from `pytest --cov`) and has a closing line for THIS issue (`Closes #<this issue's number>`), so the round closes when the PR merges.

## Acceptance Criteria

- [ ] `pytest` passes in CI with the new tests, and each new test fails when the code it covers is deliberately broken (the PR body shows the break-and-revert run).
- [ ] The PR's Gate coverage shows the targets' uncovered statements+branches down by about 180 or more, or the PR body explains each target that could not be meaningfully covered.
- [ ] Production code changes only where a test found a real bug, each one explained in the PR body.

Same contract as every round in this initiative:
1. Pick the next target by the repo's own coverage-gap ranking (escaped-defect priority, then
   churn, then uncovered mass), not by file size.
2. Every new test must FAIL when the code it covers is deliberately broken and PASS when
   reverted -- run that break-and-revert for real and report it, don't assert it.
3. Real bugs found while writing tests get fixed with a minimal, targeted diff in the same PR,
   not worked around. Watch for the negative-cache pattern (cache.get(key) is None used as a 'not yet cached' check, which can't tell 'never queried' from 'queried and got nothing') -- it has recurred independently four separate times fleet-wide already.
4. Low blast radius only -- test-only or tightly-scoped fixes, no refactors.
5. One PR per logical chunk of work.

The goal is to improve the code, not a metric. If you measure this repo at or above 90% before
starting, say so in a comment on this issue and close it without opening a PR -- do not
manufacture a fix just because a round was requested.
