# Issue #4426 regenerated coverage ranking

Checked 2026-11-06. Machine-readable fields are in `ranking.json`.
The ranking commands are Orchestrator `src/escaped_defect_priority.py` (blob `3447463191e5b2d27acf15b3ae5f45f51a9ac484`). `coverage-autopilot.py` is not in this repository. The preserved #3998 issue integers are not overwritten by this regeneration.

## Method

Sort keys are escaped-defect weight, then churn, then uncovered statements and branches. File size is not the ranking method. A revert subject weighs 3 and a fix subject weighs 1. The window is 180 days before the ranked revision's committer timestamp, in UTC. The git command is:

```bash
git log <revision> --since=<utc-anchor> --no-merges --name-only --pretty=format:%x00%s
```

Uncovered mass is `missing_lines + missing_branches`. num_partial_branches is recorded and is not the primary uncovered unit.
Issue #3998 integers are preserved. The fresh 180-day window at the pre-round commit reproduces escaped-defect weight and churn for scripts/langchain/issue_pr_context.py only. The other five targets differ, so the printed issue order is not assumed valid.

## Regenerated order

Pre-round revision `21c87da23935bb2466cb55361d3296d225a92b7e`, committer `2026-10-16T20:23:58-05:00`, since `2026-04-20T01:23:58Z`. Tier 3 uses the issue's listed units because that Gate run has no coverage.json.

| Rank | Target | Escaped-defect weight | Churn | Issue uncovered units | Snapshot match |
| --- | --- | ---: | ---: | ---: | --- |
| 1 | `scripts/langchain/pr_verifier.py` | 46 | 54 | 281 | no |
| 2 | `scripts/sync_test_dependencies.py` | 18 | 20 | 6 | no |
| 3 | `tools/langchain_client.py` | 14 | 20 | 29 | no |
| 4 | `scripts/langchain/verifier_config.py` | 8 | 10 | 16 | no |
| 5 | `scripts/langchain/task_validator.py` | 7 | 10 | 36 | no |
| 6 | `scripts/langchain/issue_pr_context.py` | 7 | 9 | 30 | yes |

Current main `d58f4aa9e54658c6f904c0cccf62dc3b094ea4e4`, committer `2026-11-06T10:54:02-06:00`, since `2026-05-10T16:54:02Z`. Tier 3 uses Gate run 42250720123.

| Rank | Target | Escaped-defect weight | Churn | Missing lines + branches | Statements |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | `scripts/langchain/pr_verifier.py` | 62 | 75 | 273 | 3188 |
| 2 | `scripts/sync_test_dependencies.py` | 17 | 20 | 6 | 339 |
| 3 | `tools/langchain_client.py` | 12 | 18 | 21 | 278 |
| 4 | `scripts/langchain/task_validator.py` | 7 | 10 | 6 | 248 |
| 5 | `scripts/langchain/verifier_config.py` | 4 | 5 | 2 | 144 |
| 6 | `scripts/langchain/issue_pr_context.py` | 2 | 3 | 19 | 359 |

Historical issue order: `scripts/sync_test_dependencies.py`, `scripts/langchain/issue_pr_context.py`, `scripts/langchain/verifier_config.py`, `tools/langchain_client.py`, `scripts/langchain/task_validator.py`, `scripts/langchain/pr_verifier.py`.
Regenerated current order: `scripts/langchain/pr_verifier.py`, `scripts/sync_test_dependencies.py`, `tools/langchain_client.py`, `scripts/langchain/task_validator.py`, `scripts/langchain/verifier_config.py`, `scripts/langchain/issue_pr_context.py`.
Current file-size order: `scripts/langchain/pr_verifier.py`, `scripts/langchain/issue_pr_context.py`, `scripts/sync_test_dependencies.py`, `tools/langchain_client.py`, `scripts/langchain/task_validator.py`, `scripts/langchain/verifier_config.py`.
The regenerated order disagrees with both the issue snapshot and file size. `scripts/langchain/issue_pr_context.py` has more uncovered units than `scripts/langchain/verifier_config.py` and still ranks lower because its escaped-defect weight is lower.

## Landed contribution and remainder

The original numerical rule remains about 180 uncovered statements and branches. This record does not replace it with another threshold.
The pre-round 90% close-without-a-PR exception is inactive: recovered coverage was below 90% when the round opened.
Counted landed reduction from #4000 and #4405: 0.
Unmerged #4405 units are not added to the #4000 gap and are not subtracted from the current Gate remainder. The issue-snapshot difference is recorded separately and is not assigned to either pull request.
Issue-listed units: 398. Current Gate units: 327. Unattributed snapshot difference: 71. That difference is not a #4000 measurement and is not added to the unmerged #4405 counters.
Lines plus partial branches on the current Gate artifact: 287. This alternate total is not the remainder.
Remainder on the current Gate artifact: 327 uncovered statements and branches across the six targets.
The counted reduction of 0 leaves the about-180 rule unmet.

| Target | Issue units | Current Gate units | Unattributed difference | Unmerged #4405 units | Counted reduction |
| --- | ---: | ---: | ---: | ---: | ---: |
| `scripts/sync_test_dependencies.py` | 6 | 6 | 0 | 8 | 0 |
| `scripts/langchain/issue_pr_context.py` | 30 | 19 | 11 | 22 | 0 |
| `scripts/langchain/verifier_config.py` | 16 | 2 | 14 | 0 | 0 |
| `tools/langchain_client.py` | 29 | 21 | 8 | 2 | 0 |
| `scripts/langchain/task_validator.py` | 36 | 6 | 30 | 6 | 0 |
| `scripts/langchain/pr_verifier.py` | 281 | 273 | 8 | 274 | 0 |

Unmerged #4405 target units sum to 312 and stay outside the remainder.
