# Issue #4426 exact-head Gate results

Checked 2026-11-06T20:44:18Z. Machine-readable fields are in `exact-head-gate.json`.
The original numerical rule remains about 180 uncovered statements and branches. This record does not replace that rule.
Uncovered units are `missing_lines + missing_branches`.
The Gate pytest command is `pytest -p ci_test_growth "${args[@]}"`, recorded in `docs/evidence/issue-4426/gate-check.md`.
coverage.py branch percent_covered: covered statements plus covered branches, over statements plus branches. pyproject.toml branch = true and source = ["scripts", "tools", "src"].

## Baseline and commits

Baseline Gate run 42250720123 tested `53351df5b25d34abd6dcb91852fafcb3b53430bd` and displays 91.08% (63216 / 69409). `coverage.json` SHA-256 `4bbdc0b3e9754e079962008e9678a4fc287d65dfe9bd8023c0435575ba49c78e`.
First green chunk head `837c3eea46c6fdb3db176534664fedabcaee9edb`, synthetic merge `0666820cde798ce3ea72eb3bdd6cdb61506e7869`, displays 91.18% (63289 / 69409).
Exact head `97fa3cdd6b198623db4adc86f16f0b3788320794`, synthetic merge `e4e584ea61852751c55749ab9ed6539fa10c9a31` (tree `c9e0d5158f0dd4bc8166c3667439219b7e943fd9`), displays 91.21% (63324 / 69426). `coverage.json` SHA-256 `6b69520f3221ba81daf73c3d30d867c70ed4f109506da15bd877e5b6edf21b92`.

## CI results

Chunk `expanded_comparison_verdict` red run 42270085183 on `e47c8e3ef1b4d49577324ce8e8702eda0315d43e` failed: 4 failed, 49842 passed, 27 skipped, 3 xfailed in 745.49s. Named failure: tests/docs/test_issue_4426_ranking.py RuntimeError: fatal: bad object 21c87da23935bb2466cb55361d3296d225a92b7e. The run failed before a comparable green artifact. Coverage from this red head was not downloaded.
Green run 42274021297 concluded success. Python 3.14 junit: 49846 passed, 27 skipped, 3 xfailed, 0 failed. Controller elapsed 733.316674 seconds.
Receipt commit `5ca0ab685a2d80c6c57b85cf0e26806a84175352` Gate run 42278384461 concluded success. That commit records deliberate-break receipts. It does not change the measured production symbols. Its coverage.json was not downloaded, so its per-file counters are unavailable here.
Chunk `client selection cache miss` red run 42283618148 on `fac11d40b0133243b35028bbcd663473403fd85a` failed: 2 failed, 49862 passed, 27 skipped, 3 xfailed in 711.36s. Named failure: tests/tools/test_langchain_client.py::test_slot_provider_override_selects_the_github_builder and test_paired_slot_provider_override_selects_the_github_builder. The run failed before a comparable green artifact. Coverage from this red head was not downloaded.
Exact-head Gate run 42287174423 concluded success on `97fa3cdd6b198623db4adc86f16f0b3788320794`. Python 3.14 junit: 49864 passed, 27 skipped, 3 xfailed, 0 failed. Controller elapsed 712.740934 seconds. Python 3.13 junit matches those pass counts, coverage.json is false, and coverage status is UNKNOWN.

## Measured reduction

Baseline target units: 327. After `expanded_comparison_verdict`: 254 (reduction 73). Exact head: 238 (further reduction 16). Round-wide target reduction: 89.
Counted function reduction: 89. The reduction of 89 leaves the about-180 rule unmet. Shortfall: 91 uncovered statements and branches.
No target is excluded. Inability to obtain a terminal receipt is not the reason any of these files remain open.

| Target | Baseline units | After first chunk | Exact-head units | Reduction | Excluded |
| --- | ---: | ---: | ---: | ---: | --- |
| `scripts/langchain/pr_verifier.py` | 273 | 200 | 200 | 73 | no |
| `scripts/sync_test_dependencies.py` | 6 | 6 | 6 | 0 | no |
| `tools/langchain_client.py` | 21 | 21 | 5 | 16 | no |
| `scripts/langchain/task_validator.py` | 6 | 6 | 6 | 0 | no |
| `scripts/langchain/verifier_config.py` | 2 | 2 | 2 | 0 | no |
| `scripts/langchain/issue_pr_context.py` | 19 | 19 | 19 | 0 | no |

## Symbol attribution

| Symbol | Counted | Baseline units | Exact-head units | Reduction |
| --- | --- | ---: | ---: | ---: |
| `scripts/langchain/pr_verifier.py:expanded_comparison_verdict` | yes | 73 | 0 | 73 |
| `tools/langchain_client.py:build_chat_client` | yes | 10 | 2 | 8 |
| `tools/langchain_client.py:build_chat_clients` | yes | 9 | 3 | 6 |
| `tools/langchain_client.py:_apply_slot_env_overrides` | yes | 1 | 0 | 1 |
| `tools/langchain_client.py:_load_slot_config` | yes | 1 | 0 | 1 |
| `tools/llm_registry.py:apply_slot_env_overrides` | no | 4 | 2 | 2 |

## Dispositions

`scripts/langchain/pr_verifier.py`: expanded_comparison_verdict is fully covered. Other functions in this file remain ordinary uncovered code, including follow-up issue creation and evidence classification. They are not dead code and they do not require an unfakeable external service.

`scripts/sync_test_dependencies.py`: Six uncovered units remain in requirement parsing and path detection. They are local filesystem logic and were not selected in the delivered chunks because they rank below the two measured symbols.

`tools/langchain_client.py`: build_chat_clients and build_chat_client still have five uncovered units after the cache-miss fix. Provider construction is already faked in tests/tools/test_langchain_client.py. The residue is not an unfakeable service.

`scripts/langchain/task_validator.py`: Six uncovered units remain on the module body, main, and refinement parsing. They are ordinary branches and were not the selected chunk.

`scripts/langchain/verifier_config.py`: latest_verifier_report still has two uncovered units. Artifact coercion and duplicate-verdict parsing already have mutation receipts. This residue is smaller than the measured functions and is not excluded.

`scripts/langchain/issue_pr_context.py`: _cap_sections still has nineteen uncovered units. The module parses local issue and pull-request context. It ranks last on escaped-defect weight and was not the delivered chunk.

`tools/llm_registry.py:apply_slot_env_overrides`: Outside the #3998 target list. Incidental coverage from the client tests. Not an exclusion and not part of the about-180 target reduction.

## Mutation receipts and stop rule

Deliberate-break receipts remain in `docs/evidence/issue-4426/mutation-receipts.md`. Production files still match the restored SHA-256 values. No mutation is left in the tree.
Each red head failed once and the following commit passed. That is one failure of each required check, not a second failure. A local rerun of the full Gate pytest was not started: the recovered Python 3.14 controller elapsed 712.740934 seconds, past the 600 second command limit. The comparable result is the downloaded exact-head artifact.
Stopping step: record exact-head Gate artifacts. Stop rule tripped: false.
Cost since the preceding report: red Gate 42283618148 (711.36s Python 3.14 pytest) and green Gate 42287174423 (712.740934s Python 3.14 controller; 626.370932s Python 3.13 controller). Local full pytest: not started.

## Follow-ups

- The about-180 target rule is still unmet. Remaining units are meaningfully testable and are not exclusions.
- tools/llm_registry.py apply_slot_env_overrides lost two uncovered units incidentally. It is outside the #3998 list and is not counted.
- Gate run 42278384461 on the receipt commit succeeded, and its coverage.json was not downloaded.
- The red ranking failure was a missing pre-round git object on the runner. The red client failure was two provider-override assertions. Both were fixed by later commits on this branch and are not reopened here.
