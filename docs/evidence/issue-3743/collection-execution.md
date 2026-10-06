# Collection regression execution evidence

The first acceptance criterion remains blocked: `/opt/anaconda3/bin/python3`
is absent on this runner. The [literal command attempt](automation/collection-execution/requested-interpreter.txt)
records exit 127. Available Python results do not satisfy that exact-path criterion.

The test-only follow-up adds an independent execution record to
`test_base_collection_failure_cannot_prove_a_deliberate_break`. The record lives
outside the archived repository, survives cleanup, and requires exactly one
head test execution and zero base executions. Both root and consumer helper
variants retain the missing-module and stdout/stderr assertions.

## Observed mutation proof

| Experiment, across both helper variants | Failed | Passed |
| --- | ---: | ---: |
| Exact prior false-PASS implementation (`5656aa96`) | 2 | 0 |
| Report head success without executing its command | 2 | 0 |
| Restore current helpers byte-identically | 0 | 2 |

The skipped-head mutation fails the added execution assertion in both cases.
The prior implementation fails the existing verdict assertion. Commands,
per-parameter logs, mutation diffs, reproduction driver, and source/test hashes
are retained in the [automation evidence directory](automation/collection-execution/).
The [manifest](automation/collection-execution/mutation-manifest.json) confirms
byte-identical restoration of both helpers, with shared SHA-256
`704ce62c2b3d0470476571d3703799b8c9aac73a74ed7a0e61ea772fdd6f749a`.

## Validation

The [before](automation/collection-execution/coverage-before.txt) and
[after](automation/collection-execution/coverage-after.txt) targeted coverage runs
both pass **200 tests**, with no failures or skips, using Python 3.14.7.
Focused helper coverage remains **90.71%**: statements **91.41%** (532/582),
branches **89.15%** (230/258). Both coverage JSON files are retained. This
does not establish a new whole-repository coverage measurement.

[Checks](automation/collection-execution/checks.txt) pass template sync,
template completeness, focused Black/Ruff, whitespace validation and helper
byte identity. The stock repository-wide Black command stalled and was
interrupted. The previously retained serial dispatch adapter invokes Black's
unchanged formatter and checks with the required CLI options; all **661 files**
pass, as recorded in the [formatting log](automation/collection-execution/black-all.txt).

## Acceptance reconciliation and handoff

The recent commits `41920a5e`, `9b05de86`, and `3d1fb32f` already retain the
collection/import, both-stream, exit-code and behavioral-control proofs.
Their [execution evidence](test-execution.md) verifies all unchanged cases.
This follow-up independently verifies head execution for the collection case.

- [ ] Run the literal Anaconda-interpreter acceptance command where that interpreter exists.
- [x] Real collection regression covers both helpers, missing module, both streams and prior-code RED.
- [x] Exit 2/3/4/5 and genuine in-test import cases have retained per-parameter RED/GREEN evidence.
- [x] Template validation, focused Black/Ruff, whitespace checks and helper byte identity pass.

GitHub rejected the PR body reconciliation, blocker comment and `needs-human`
label because each requires approval while this run's approval policy is `never`.
No remote checklist, comment or label changed. The prepared reconciled PR body
is retained at `/tmp/pr-3775-reconciled-body.md` for the owning lane to apply.

The original Git metadata is read-only. The source/evidence commit uses the
writable Git directory `/tmp/workflows-collection-execution-3775.git`, with
bundle handoff `/tmp/workflows-collection-execution-3775.bundle`. Remote
publication and the literal interpreter check remain pending.
