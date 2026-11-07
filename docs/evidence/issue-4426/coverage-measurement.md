# Issue #4426 repository coverage measurements

Checked 2026-11-06. Machine-readable fields are in `coverage-measurement.json`.
The accounting is coverage.py's branch `percent_covered`: covered statements
plus covered branches, divided by statements plus branches. `pyproject.toml`
`[tool.coverage.run]` is identical at opening main
`21c87da23935bb2466cb55361d3296d225a92b7e` and current main
`d58f4aa9e54658c6f904c0cccf62dc3b094ea4e4`: `branch = true` and
`source = ["scripts", "tools", "src"]`. `coverage.xml` `line-rate` stays the
statement ratio. The original about-180 uncovered-statement-and-branch rule is
unchanged.

## Issue snapshot and recovered pre-round CI

Issue #3998 opened 2026-10-17T01:44:12Z. Its opening sentence says Workflows
read 82.29% blended line and branch coverage, with about 4488 statements plus
branches still required to reach 90%. That sentence is the issue snapshot.

Opening main at that time is `21c87da23935bb2466cb55361d3296d225a92b7e` (tree
`f0d2a1c1adfc78cc86eebf4c30bf70efc418851a`). Selftest CI run
[38990686823](https://github.com/stranske/Workflows/actions/runs/38990686823)
succeeded on that commit and reports artifact `total_count` 0. That selftest
ran a subset pytest and did not call `reusable-10-ci-python.yml`.

The recovered whole-suite Gate run is
[38980711116](https://github.com/stranske/Workflows/actions/runs/38980711116),
pull request #3965, head `8abd5ec784c97572b2f8baf99e0157bf64728fbb` (tree
`670c55bff2b326eaa74fdf147ee3cf62715632d6`). That head was squash-merged as the
opening main commit. The two trees differ, and this Gate run is the last
whole-suite measurement recovered before the issue opened. Its artifact
`total_count` is 0, so `coverage.json` is unavailable. The job logs still
contain the term-report totals.

The Pytest step ran `pytest "${args[@]}"` with marker
`not quarantine and not slow`, `--cov`, `--cov-config=pyproject.toml`,
`--cov-report=xml:coverage.xml`, `--cov-report=term-missing`,
`--cov-report=json:coverage.json`, `-n auto`, and `--dist=loadgroup`. Python
versions were 3.12 and 3.13. `coverage-min` was empty. This step did not yet
call `pytest -p ci_test_growth`.

| Runtime | Job | Statements | Missed statements | Branches | Partial branches | Display |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Python 3.12.15 | 117244209085 | 41734 | 6689 | 16944 | 2477 | 81.83% |
| Python 3.13.16 | 117244209133 | 41734 | 6687 | 16944 | 2474 | 81.84% |

Both jobs reported `106043 passed, 25 skipped, 3 xfailed`. Partial branches are
the term-report `BrPart` column. Missing branch outcomes were not printed, and
the missing `coverage.json` leaves those outcomes unavailable. The contract
says to use CI's number when a baseline differs: these displays are 81.83% and
81.84%, and the issue snapshot is 82.29%.

## Current Gate and main

Current `origin/main` is `d58f4aa9e54658c6f904c0cccf62dc3b094ea4e4` (tree
`d35e41d87be75f95d898b01de0b4d0d9591db73f`). This branch's main ancestor is
`7b92760527da7c9a7a5282005009b75f7d01cd2e`.

Gate run [42250720123](https://github.com/stranske/Workflows/actions/runs/42250720123)
is pull request #4477. The run head is
`21453e987b903855574e6655ace2c63fde0d9eda`. Pytest's checkout `HEAD` was the
synthetic merge `53351df5b25d34abd6dcb91852fafcb3b53430bd` (tree
`58c0a65adc6a760be54bf2508cb61da798f97076`), recorded as `tested_sha`. The
Python 3.14 job 128005600052 succeeded and printed:

`49555` statements, `3718` missed, `19854` branches, `1841` partial, `91.08%`.

Pytest summary: `49813 passed, 27 skipped, 3 xfailed in 696.42s`.

The downloaded `gate-coverage-3.14-1` `coverage.json` is 3,927,058 bytes,
SHA-256 `4bbdc0b3e9754e079962008e9678a4fc287d65dfe9bd8023c0435575ba49c78e`,
coverage.py 7.17.2, branch coverage on. Counters:

- covered statements `45837`, missed statements `3718`, statements `49555`
- covered branches `17379`, missed branch outcomes `2475`, branches `19854`
- partial branches `1841`
- blended `(45837 + 17379) / (49555 + 19854) = 63216 / 69409` = 91.07752596925471% (display 91.08%)
- statement `percent_statements_covered` 92.49722530521643%
- `coverage.xml` `line-rate` `0.925`

Python 3.13 in that Gate run has `coverage_json: false`. Gate's
`coverage-python-version` is `3.14`. The invocation is
`pytest -p ci_test_growth "${args[@]}"` with the same marker, coverage reports,
`pyproject.toml` config, four workers, and `--dist=loadgroup`.

Selftest CI run [42256644648](https://github.com/stranske/Workflows/actions/runs/42256644648)
is the push of `d58f4aa9e54658c6f904c0cccf62dc3b094ea4e4`. Its Python 3.14 job
128025899481 printed the same term total and the same pytest pass counts
(`49813 passed, 27 skipped, 3 xfailed`). `tested_sha` equals that push.
`selftest-coverage-3.14-1` `coverage.json` is also 3,927,058 bytes, SHA-256
`705ef640054658362278b7edb407418c2b72bd91392d9b9f8336d694f12e1e9f`. The integer
totals equal the Gate file. Selftest leaves `coverage-python-version` empty and
sets primary Python to 3.13; the comparable artifact is still the Python 3.14
bundle from the same reusable Pytest step.

## 90% contract decision

The #3998 exception applies when repository coverage is already at least 90%
before the round starts. The recovered pre-round displays, 81.83% and 81.84%,
are below 90%. The issue snapshot, 82.29%, is also below 90%. The exception
does not apply, and it does not cancel the about-180 remainder. Current
blended coverage is 91.08%, measured after the round opened. Later tasks still
owe a target-level remainder against the original numerical rule. The same-artifact
target counters are stored beside the repository totals for that later ranking;
they are not themselves the round-wide reduction.

## Later log reconciliation, 2026-11-07

The historical records above remain unchanged. `gate-report-inputs.json` pins
bounded per-target log excerpts from original Gate jobs 117244209085 (3.12)
and 117244209133 (3.13), plus final-head job 128131232558 (3.14). Selected
REST metadata binds run 42287174423 and artifact 13537639987 to PR #4481 head
`97fa3cdd6b198623db4adc86f16f0b3788320794`. The actual tested checkout is
`e4e584ea61852751c55749ab9ed6539fa10c9a31`, tree
`c9e0d5158f0dd4bc8166c3667439219b7e943fd9`; its parents are base
`d216eaafb02c97ed5f1da16a10d46d9a967c616f` and that PR head.

Each small target report permits exactly one integer missing-branch count
under coverage.py's precision-two display. The evidence test enumerates every
valid missing-branch count, requires a unique match, and rejects ambiguous
totals, impossible counters, missing/duplicate targets, or mismatched identities.
It does not use partial branches as missing branch outcomes. The original
Python 3.12 and 3.13 target counters agree:

| Target | Original missing lines | Original missing branches | Final missing lines | Final missing branches |
| --- | ---: | ---: | ---: | ---: |
| `scripts/sync_test_dependencies.py` | 1 | 5 | 1 | 5 |
| `scripts/langchain/issue_pr_context.py` | 17 | 13 | 13 | 6 |
| `scripts/langchain/verifier_config.py` | 7 | 9 | 1 | 1 |
| `tools/langchain_client.py` | 21 | 8 | 3 | 2 |
| `scripts/langchain/task_validator.py` | 25 | 13 | 3 | 3 |
| `scripts/langchain/pr_verifier.py` | 169 | 114 | 107 | 93 |

Original log-derived missing units total **402**; final log-derived missing
units total **238**. Their difference, **164**, is an unattributed snapshot
difference, not an attributable round-wide reduction. The issue-listed 398
units and the earlier downloaded Gate's 327 units remain separate snapshots.
No target exclusions are claimed and no units are credited toward acceptance.

These are reconstructed counters from the recorded Gate configurations, not
comparable downloaded artifacts or branch arcs. Original Gate used Python
3.12/3.13, `pytest`, and automatic workers; final Gate used Python 3.14,
`pytest -p ci_test_growth`, and four workers. Source and test inventories also
changed (for example, verifier statements grew from 2586 to 3188). The current
coverage configuration alone does not establish equivalent execution.
The repository-wide final TOTAL has several possible missing-branch counts
at its rounded percentage; no exact total is inferred. The final archive URL
still fails local DNS resolution. `attributable_round_reduction` and the
**comparable** original-round baseline remain null. Task 1 stays incomplete
until comparable artifacts establish attribution against the about-180 rule.

Reproduce the offline counter and identity checks:

```bash
python -m pytest -q tests/docs/test_issue_4426_coverage_measurement.py tests/docs/test_issue_4426_ranking.py -m 'not slow'
```
