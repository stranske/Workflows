# Issue 4019 integration acceptance (PR for #4433)

Written to `acceptance-integration.md` rather than `acceptance.md` because
PR #4431 already adds `docs/evidence/issue-4019/r3/acceptance.md`; a second
copy would be an add/add conflict when #4431 merges.

## Task 1: #4431 state

- Acceptance date: 2026-11-06 (readback via `gh pr view 4431`).
- Checked head: `69e5b6d6cd3fb154be29890f2ae212772de8ce45`
- State: OPEN, `mergeCommit: null`, mergeable MERGEABLE, base `main`
  (branch `closer-r3/issue-4019`). Not delivered on main.
- Hosted checks on that head: Gate / gate, python ci / python 3.13 and 3.14,
  slow compatibility 3.13/3.14, CodeQL, Semgrep, test-quality: SUCCESS.
- `docs/AGENT_ISSUE_FORMAT.md` does not exist at repo root; only
  `templates/consumer-repo/docs/AGENT_ISSUE_FORMAT.md` does.

## Task 2 (partial): previously merged work

- #4021 merge commit `5dee9a65400f` and #4406 merge commit `2bd1aa094698`
  are both ancestors of `origin/main` (`git merge-base --is-ancestor`).
- Test function counts, main vs #4431 head: aggregate 71 -> 74,
  sync drift 66 -> 66, llm_provider 91 -> 112. No test file shrinks.
- Main's `tools/llm_provider.py::_supports_quality_context` still has
  `if supports is not None` after the `try/except`; #4431 changes it to
  `elif`. The raising-helper fix is therefore not on main.

## Task 2 (complete): retention verified

- `gh pr view 4021` -> MERGED, `5dee9a65400f`; adds 18/55/13 lines (all
  additions) to `tests/scripts/test_aggregate_agent_metrics.py`,
  `tests/scripts/test_check_consumer_sync_drift.py`,
  `tests/tools/test_llm_provider.py`.
- `gh pr view 4406` -> MERGED, `2bd1aa094698`; adds the 33 files under
  `docs/evidence/issue-4019/` (additions only, plus one line in
  `.github/workflows/autofix-versions.env`).
- #4431 file list (`gh pr view 4431 --json files`): the only files with
  deletions are `tools/llm_provider.py` (1+/1-, the `if` -> `elif` fix). Tests
  gain +29 (aggregate) and +221 (llm_provider) lines with 0 deletions, the
  sync-drift test is untouched, and all new evidence lives under
  `docs/evidence/issue-4019/r3/`, so no existing evidence file is overwritten.
- Conclusion: delivered behavior from #4021/#4406 is retained on main and is
  not removed or altered by #4431.

## Task 3: raw Gate coverage per target

Script: `docs/evidence/issue-4019/r3/target_missing.py` (from #4431 head
`69e5b6d6`; not on main yet). Syntax inspected: `python -I target_missing.py
<coverage.json>`; it reads `totals` and per-file `summary.missing_lines` /
`missing_branches`. Run from `/tmp/scripts` against artifacts downloaded
(`gh run download <run> -n gate-coverage-<py>-1`) into fresh `/tmp/art/<run>-<py>/`.
Artifacts are not expired. All three runs: workflow `Gate`, conclusion success.

| Run | Gate head SHA | Role |
|---|---|---|
| 41557902073 | `4800afb5c97f` | earlier baseline (2026-11-03) |
| 41668857273 | `79c84f753656` | baseline in #4431 evidence |
| 41717668636 | `f485bbc251a7` | head in #4431 evidence |

Denominator = `num_statements + num_branches` (branch coverage on, coverage 7.17.x).
Missing = missing statements + missing branches, three targets only.

### Python 3.14 (only runtime with coverage data)

| Run | Total covered/units (denominator) | aggregate_agent_metrics | check_consumer_sync_drift | llm_provider | Target missing | pytest tests / time |
|---|---|---|---|---|---|---|
| 41557902073 | 62986 / 69223 (90.99%) | 0+3 | 0+0 | 77+27=104 | 107 | 50339 / 711.6s |
| 41668857273 | 63040 / 69241 (91.04%) | 0+3 | 0+0 | 54+16=70 | 73 | 50377 / 691.5s |
| 41717668636 | 63110 / 69241 (91.15%) | 0+0 | 0+0 | 3+0=3 | 3 | 50403 / 668.9s |

Residuals at run 41717668636 (3.14): `tools/llm_provider.py` lines 265, 270, 292
(3 statements, 0 branches). Run 41668857273 residuals for aggregate were
branches 492->481, 954->910, 1011->996, all closed by 41717668636.

### Python 3.13 (discrepancy)

`summary.json` for every run shows `coverage_json: false`, `coverage_xml: false`,
`coverage_minimum: skipped`; the 3.13 artifact has no `coverage.json`. Gate runs
coverage only on 3.14, so **no per-runtime comparable 3.13 baseline/head missing
count exists in these artifacts**; the script cannot run on 3.13. Tests passed
on 3.13 (50339 / 50377 / 50403 tests, 0 failures, 30 skipped; junit 632.5s /
629.0s / 628.6s). The acceptance criterion's "separately report each runtime"
is therefore only satisfiable as: 3.14 measured, 3.13 not measured by Gate.
(`index.ndjson` in each artifact carries accumulated historical entries with
92.xx percentages; they are not per-run and were not used.)

### Residual explanation (3.14, head)

The three llm_provider lines (265, 270, 292) are still uncovered at the Gate
head `f485bbc`; #4431's later commits (head `69e5b6d6`) may change this and
were not measured by a Gate coverage run in this task. Behavioral explanation
of those lines remains for the per-target explanation review.
