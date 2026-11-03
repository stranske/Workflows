# Round 17 closer evidence recovery

Checked 2026-11-03. Refs #4161. This is evidence for the tests already delivered
by [#4163](https://github.com/stranske/Workflows/pull/4163); it does not replace
that implementation. No production or test files are changed by this repair.
The provisioned branch started clean at
`6cf49cb29e356e1f400849dea36521c9647a2894` (current main at initial fetch).
There was no partial work to discard.

Acceptance outcome: every added test case detects a recorded production
mutation and passes after restoration; recovered Gate CI passes; the measured
target delta and historical ranking are explicit. The named-suite command
below prints the passing result. Stop rule for this recovery: two failed
acceptance attempts at a required evidence step, or 60 minutes elapsed.

## Revisions and recovered CI

* Merge parent: `df108f233ea978e1788dc6b2b60e641e69fa5794`.
* Merged revision: `d2def1901357855222046823b609a8f87b95ccfb`.
* Original final PR head: `4bb59235d403cb3d39a364be8d987cd558d61a9a`.
* Gate tested the synthetic merge
  `67e785735e481d7da5af4f559bb4a467b4c1a876`, combining that final head and
  the merge parent. This is distinct from the eventual squash commit.
* [Gate run 39472016026](https://github.com/stranske/Workflows/actions/runs/39472016026)
  concluded success. The Python
  [3.14 job](https://github.com/stranske/Workflows/actions/runs/39472016026/job/118798576499)
  reports `52071 passed, 27 skipped, 3 xfailed in 546.51s`;
  [3.13](https://github.com/stranske/Workflows/actions/runs/39472016026/job/118798576536)
  reports the same counts in 405.68s. Both pytest steps, lint-ruff,
  lint-format and typecheck-mypy succeeded.

The complete original PR body and discussion were retrieved before replay.
Its grouped break-and-revert statements remain historical claims; they are
preserved in the evidence bundle rather than silently replaced with invented
terminal records. Fresh per-case records supply the missing raw proof.
The aggregate Git diff has all four named test files, 2,060 insertions and
eight deletions. The verifier's contradictory missing-file descriptions do
not establish a missing implementation.

Both the connector and paginated REST artifact listing now return
`{"total_count":0,"artifacts":[]}`. The recovered job log records successful
coverage uploads with seven-day retention; this check is fourteen days later.
Expiry is consistent with that evidence, but deletion cause was not verified.
The surviving CI log includes all four target coverage rows and the whole-suite
total: **87.73%**. No complete historical baseline coverage artifact was recovered.

## Target selection

The authoritative historical selection is the scope of
[#4161](https://github.com/stranske/Workflows/issues/4161), not a fresh ranking
computed after the work. Sort order is escaped-defect signals, then churn,
then uncovered statement-plus-branch mass. Each target had a fix commit touch.

| Rank | Target | Escaped-defect signals | Churn | Issue's CI uncovered units |
| --- | --- | ---: | ---: | ---: |
| 1 | `scripts/check_consumer_sync_drift.py` | 6 | 14 | 69 |
| 2 | `scripts/validate_run_contract.py` | 4 | 7 | 26 |
| 3 | `scripts/langchain/issue_formatter.py` | 3 | 6 | 29 |
| 4 | `tools/post_ci_summary.py` | 3 | 3 | 88 |

The 212-unit bundle exhausted the four selected targets. File size was not the
selection rule. The issue supplies the historical ranking; the original
fleet-ranking generator's raw inputs were not recovered independently.

## Replayed coverage and its limits

No `.venv` or other repository-selected interpreter was present in the
provisioned worktree. Per the owner's runtime rule, local runs used
`/opt/anaconda3/bin/python3` (Conda Python 3.12.2, pytest 9.1.1, coverage 7.16.2).
This differs from hosted Gate's Linux/Python 3.14 environment and the project's
declared Python >=3.13. The recovered hosted CI, rather than this local replay,
establishes supported-runtime CI success.

Both historical trees were extracted with `git archive REV | tar -x -C DIR`
under `/tmp/wf4161-recovery/{parent,merged}`. Their own `pyproject.toml` pytest
and coverage configuration and Gate marker expression were used unchanged.
These are focused runs of the four requested files plus the contract tests
already named by #4163. They are not whole-suite Gate reruns. Gate's xdist,
test-growth plugin and CI cache were not reproduced.

Run this command inside each extracted tree, replacing `LABEL` with `parent`
or `merged` (the merged run additionally used `--cov-context=test` to choose
executed mutation sites):

```bash
/opt/anaconda3/bin/python3 -m pytest \
  -m 'not quarantine and not slow' --cov --cov-config=pyproject.toml \
  --cov-report=json:/tmp/wf4161-recovery/LABEL-coverage.json \
  --cov-report=xml:/tmp/wf4161-recovery/LABEL-coverage.xml \
  --cov-report=term-missing --junitxml=/tmp/wf4161-recovery/LABEL.xml \
  tests/scripts/test_check_consumer_sync_drift.py \
  tests/scripts/test_issue_formatter.py \
  tests/scripts/test_validate_run_contract.py \
  tests/test_post_ci_summary.py tests/contracts/test_validate_run_contract.py -q
```

Output: parent **300 passed in 43.52s**; merged **391 passed in 45.37s**.
Count **missing statements + missing branch outcomes**, not `Miss + BrPart`:
the latter can undercount branches in wholly unexecuted code.

| Target | Statements / branch outcomes | Parent missed statements / branches | Merged missed statements / branches | Reduction | Recovered Gate after |
| --- | ---: | ---: | ---: | ---: | ---: |
| Consumer drift | 633 / 296 | 33 / 37 | 0 / 0 | 70 | 100.00% |
| Run contract | 448 / 212 | 12 / 14 | 0 / 0 | 26 | 100.00% |
| Issue formatter | 447 / 174 | 12 / 17 | 0 / 0 | 29 | 100.00% |
| Post-CI summary | 680 / 352 | 44 / 48 | 1 / 2 | 89 | 99.71% |
| Total | 2,208 / 1,034 | 101 / 116 | 1 / 2 | **214** | **99.91% target blend** |

The local like-for-like reduction is **217 -> 3 = 214 units**, exceeding 180
by 34. The historical issue ranking gives **212 -> 3 = 209** (29 above 180),
but its baseline is a different whole-suite measurement and cannot be treated
as a freshly reproduced like-for-like Gate delta. The after rows independently
agree with the surviving Gate log. Neither figure means this documentation PR
adds coverage, or that repository-wide coverage reached 90%.

Remaining target limits: `tools/post_ci_summary.py:751` (the duplicate-name
`continue`) and missing branches `[748,755]`, `[750,751]`. The first candidate
enters an empty `seen` set and then unconditionally breaks. Consequently the
duplicate path and natural loop exit are unreachable with the current control
flow. No production change, exclusion or unrelated tests were added to remove
these three units. There is no measured shortfall against the selected 180-unit
goal; exact historical whole-suite baseline recovery remains unavailable.

## Deliberate break and restore

The compressed evidence bundle records exact commands, source replacements,
failing case IDs, JUnit, stdout and SHA-256 restoration hashes. All source
mutations ran in isolated archives, never in the repair branch. Every accepted
RED is pytest exit 1 with a named test failure, not a collection error; its
paired restored GREEN is exit 0. Exploratory mutants that survived are retained
as attempts and are not counted as proof. Mutation detection establishes a
counterexample per case, not exhaustive mutation adequacy.

Additional targeted mutations distinguish repository cache identity, reuse of
cached `None` and empty text, all three time-boundary cases, missing remote-file
reporting and filtering unknown repositories. Each is restored before rerun.
The original tests required no strengthening to detect these mutations.

The current-main four-file command also passed before any evidence edits:

```bash
/opt/anaconda3/bin/python3 -m pytest -m 'not quarantine and not slow' \
  tests/scripts/test_check_consumer_sync_drift.py \
  tests/scripts/test_issue_formatter.py \
  tests/scripts/test_validate_run_contract.py tests/test_post_ci_summary.py \
  -q --junitxml=/tmp/wf4161-recovery/current.xml
```

Output: **300 passed in 18.21s**. Later main changes account for this suite's
different composition; it must not be confused with the historical merged
revision plus contract-suite count of 391.

Fresh proof: **86 new functions / 91 new cases detected**, plus **7 targeted
mutation pairs**. Every accepted RED has exit 1 and a named failed case; every
restored GREEN has exit 0. The final restored historical suite reports **391
passed**. Both mutation archives match the merged commit byte for byte for all
four production targets. See `acceptance.json` in the bundle.

Bundle: [proof.tar.gz](proof.tar.gz), SHA-256 `6bcf1abac025a171fd6650f0d222bbabdde55b634b83eb1f759c81273cbe3056`.
The internal `SHA256SUMS.json` validates every payload file.

The bundle retains the four-target coverage extraction; full coverage JSON and
context data remain in the local recovery directory. Regenerate them with the
recorded parent/merged commands (including `--cov-context=test` for merged)
before rerunning the exploratory mutation selector.
