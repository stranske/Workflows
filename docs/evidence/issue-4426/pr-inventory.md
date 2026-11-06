# Issue #4426 evidence: PR #4000 and PR #4405 inventory

Checked 2026-11-06. Machine-readable fields are in `pr-inventory.json`.
Complete retrieved bodies are `pr-4000.body.md` and `pr-4405.body.md`.

Observed `origin/main` at this check: `d58f4aa9e54658c6f904c0cccf62dc3b094ea4e4`.
This branch's main ancestor is `7b92760527da7c9a7a5282005009b75f7d01cd2e`.

## PR #4000

Merged, not draft. Head `faab1a08c210db85b803f4a54af408cc60bf792d`.
Merge commit `5b1c6424716c413871d4eda7f6a125fa070e097f` is on the observed main.
The head commit exists on GitHub and is absent from this clone. Merged at
2026-10-17T04:35:51Z.

The diff adds three tests to `tests/scripts/test_verifier_config.py` and no
production code:

- `test_is_terminal_artifact_handles_nested_lists_payloads_and_non_artifacts`
- `test_terminal_artifact_coercion_and_pending_stage_edges`
- `test_artifact_text_without_report_marker_and_duplicate_verdicts`

All three are present on the observed main and in this branch. Do not add them
again.

Exact-head CI:

- Gate run [39003191738](https://github.com/stranske/Workflows/actions/runs/39003191738)
  succeeded. `gh run view` reports `headSha` `faab1a08c210db85b803f4a54af408cc60bf792d`.
  Python 3.12 and Python 3.13 jobs passed.
- Selftest run [38993296895](https://github.com/stranske/Workflows/actions/runs/38993296895)
  succeeded on the same head.

Coverage artifacts: unavailable. Both runs report artifact `total_count` 0, so
`gh run download` has nothing to recover. That is missing evidence. It is not a
measured coverage delta for #4000.

## PR #4405

Open, not draft, not merged. No merge commit. Head
`a60b49b4944297401630ddb31a733c61d74fc2c1` is not on the observed main. Base
`3e513d30e1b11b30bd6a2fdc224adbca97d85930`. The pull_request synthetic merge is
`a1908589812a0bf736c52a8a2f61c69034582921`.

The diff adds 20 tests across four files and no production code. None of those
test functions are on the observed main. `tests/scripts/test_pr_verifier_diff_path_parsing.py`
does not exist on main. The #4405 changes have not landed and must not be
counted as a main contribution.

Exact-head Gate run [41572113305](https://github.com/stranske/Workflows/actions/runs/41572113305)
failed. `gh run view` reports `headSha` equal to the PR head. Python 3.13 and
Python 3.14 pytest each passed: 50366 tests, 0 failures, 0 errors, 30 skipped.
`python ci / lint-ruff` failed with
`tests/tools/test_langchain_client.py:1391:5: F841 Local variable FakeChatOpenAI is assigned to but never used`.
The summary job failed after that. Lint, Format & YAML Validation on run
41572113341 also failed.

Coverage artifacts were downloaded with
`gh run download 41572113305 --repo stranske/Workflows`. Python 3.14
`coverage.json` is present (3,912,536 bytes, SHA-256
`165ded8b0e301705966a8ec99b690d6a734c2092b5b8e311ab62c7fe6f1174a4`, coverage.py
7.17.0, branch coverage on). `gate-summary.md` in that run names the synthetic
merge commit, and `coverage.json` has no git SHA. These counters describe the
unmerged run, not main.

Blended statement-plus-branch accounting from that 3.14 file is
`(45694 + 17321) / (49421 + 19802) = 63015 / 69223` (display 91.03%).
`summary.json` reports 92.46, which is `percent_statements_covered`, not the
blended figure. Missing statements plus missing branch outcomes are
`3727 + 2481 = 6208`. Missing statements plus partial branches are
`3727 + 1837 = 5564`. The original #3998 rule remains about 180 uncovered
statements and branches. This inventory does not replace that rule.

Python 3.13 coverage JSON and XML were not in the artifact.
`summary.json` records `coverage_json: false` and `coverage_xml: false`.
Pytest junit for 3.13 was recovered. No 3.13 line or branch counters are
available.

Unmerged 3.14 target counters (missing lines / missing branches / partial branches):

| Target | Missing lines | Missing branches | Partial branches |
| --- | ---: | ---: | ---: |
| `scripts/sync_test_dependencies.py` | 3 | 5 | 5 |
| `scripts/langchain/issue_pr_context.py` | 13 | 9 | 5 |
| `scripts/langchain/verifier_config.py` | 0 | 0 | 0 |
| `tools/langchain_client.py` | 1 | 1 | 1 |
| `scripts/langchain/task_validator.py` | 3 | 3 | 3 |
| `scripts/langchain/pr_verifier.py` | 158 | 116 | 80 |

`verifier_config.py` is fully covered in this unmerged run. That measurement
is not a landed main result.
