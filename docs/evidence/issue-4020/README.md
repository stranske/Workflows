# Coverage evidence for stranske/Workflows#4020

Refs #4020. Test PR: #4022 (merge `6375427df`). Measurement only; no tests or production code changed.

## Command

Run at each commit, with the test files that import the three targets (the full suite was not run locally):

```
/opt/anaconda3/bin/python3 -m pytest tests/test_post_ci_summary.py tests/scripts/test_repo_review_coordinator.py \
  tests/scripts/test_verifier_config.py tests/scripts/test_pr_verifier_config_and_report.py \
  tests/scripts/test_repo_review_round1_runner.py tests/scripts/test_repo_review_docs_drift_scan.py \
  tests/workflows/test_maint46_post_ci_sparse_checkout.py -q -p no:cacheprovider \
  --cov=scripts.repo_review_coordinator --cov=scripts.langchain.verifier_config --cov=tools.post_ci_summary \
  --cov-branch --cov-report=term-missing --cov-report=json:<out>.json
```

Uncovered units per file = (num_statements - covered_lines) + (num_branches - covered_branches), taken from each file's `summary` in the JSON.

## Main (`2bd1aa094`) vs. judge baseline `2419bccd8`

| File | Stmts b/a | Branches b/a | Uncovered before | Uncovered after | Delta |
|---|---|---|---|---|---|
| `scripts/langchain/verifier_config.py` | 135/144 | 62/70 | 1 | 2 | -1 |
| `scripts/repo_review_coordinator.py` | 710/710 | 230/230 | 246 | 32 | 214 |
| `tools/post_ci_summary.py` | 680/680 | 352/352 | 92 | 3 | 89 |
| **Total** | | | 339 | 37 | **302** |

The 302 is cumulative. Between `2419bccd8` and main, other test PRs also touched these targets (#4056, #4146, #4147, #4163, #4169, #4183). `verifier_config.py` also gained 9 statements and 8 branches from #4037, #4129 and #4218, so its -1 is new code, not lost coverage.

## What #4022 delivered on its own (`6375427df^` vs. `6375427df`)

| File | Stmts b/a | Branches b/a | Uncovered before | Uncovered after | Delta |
|---|---|---|---|---|---|
| `scripts/langchain/verifier_config.py` | 135/135 | 62/62 | 1 | 0 | 1 |
| `scripts/repo_review_coordinator.py` | 710/710 | 230/230 | 246 | 175 | 71 |
| `tools/post_ci_summary.py` | 680/680 | 352/352 | 92 | 88 | 4 |
| **Total** | | | 339 | 263 | **76** |

So #4022 removed **76** units by itself. That is short of 180, consistent with the issue's estimate of about 100-130. The about-180 reduction across the three targets has been reached on main through #4022 plus the later PRs. Only **37** uncovered units remain across all three targets, so no further PR could be credited with another 104.

## Residual uncovered units on main (37)

- `scripts/langchain/verifier_config.py` (2): line 184. A branch added after #4022 (by #4218), outside #4020's scope.
- `tools/post_ci_summary.py` (3): `749->756`, `752`. One fallback branch in the rendering loop.
- `scripts/repo_review_coordinator.py` (32):
  - `1514-1516` and `1540-1542`: `except ModuleNotFoundError` import fallbacks for running from a steward checkout outside the package. Exercising them means faking import failure of an in-repo module, which would be a contrived test.
  - The remaining items are mostly one-sided partial branches (loop-never-entered / false arm: `532->537`, `552->576`, `567->570`, `623->673`, `717->722`, `874->877`, `884->890`, `896->877`, `1069->1088`, `1204->1304`, `1368->1380`).
  - Small error paths: `215-216` (malformed JSON), `391` (no prior cycle), `578`/`582-583` (related-log skip), `824`, `865`, `1130`.
  - These are coverable. Per the judge's step 2 they were not added, because the cumulative delta already passes 180.

## Per-test break-and-revert evidence for #4022

- https://github.com/stranske/Workflows/pull/4022#issuecomment-6233950064 (original-head causal controls)
- https://github.com/stranske/Workflows/pull/4022#issuecomment-6233973602 (current-head causal acceptance evidence)
- https://github.com/stranske/Workflows/pull/4022#issuecomment-6234011741 (UTC-midnight fixture flake fix)

## Prior local attempt

Branch `closer/issue-4020` (`e2c9bf2aa`) added a root-level `MUTATION_TEST_REPORT.md`. It was **discarded**: it claimed "approximately 180+" without a baseline measurement and stated that the delta could not be computed locally. Both points are contradicted by the tables above.
