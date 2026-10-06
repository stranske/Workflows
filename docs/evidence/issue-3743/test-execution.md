# Archived-base test execution acceptance

The first unchecked acceptance criterion is blocked: `/opt/anaconda3/bin/python3`
does not exist on this runner. The [literal launch output](automation/test-execution/requested-interpreter.txt)
records exit 127. The available interpreter is
`/opt/hostedtoolcache/Python/3.14.7/x64/bin/python3`; its results do not satisfy
the requested Anaconda path.

This test-only follow-up advances the execution acceptance criterion.
`test_base_pytest_must_execute_a_test_before_counting_as_red` now records calls
to the actual pytest execution hook in a file outside the archived repository.
Each exit 2/3/4/5 case requires exactly one head call and no base call.
`test_base_missing_import_inside_a_test_still_proves_red` records execution of
both head and base test bodies and checks genuine failure diagnostics routed
to either stdout or stderr. All cases run against both root and consumer helpers.
No production change was justified.

## Observed mutation proof

| Experiment across both helpers | Failed | Passed |
| --- | ---: | ---: |
| Exact prior false-PASS implementation at `5656aa96` | 14 | 4 |
| Remove collection corroboration from the import classifier | 4 | 0 |
| Report head success without executing its command | 12 | 0 |
| Restore current helpers | 0 | 18 |

The prior implementation's four passing cases are the genuine in-test failure
controls, now covering both streams. The head mutation fails the new execution
record assertions, establishing that they detect a skipped head command even
when existing verdict assertions would have passed. Every selected parameter
case fails under an observed source mutation and passes after restoration.

Commands, exits, per-case transcripts/JUnit, zero-context mutation diffs,
test/source hashes and the [reproduction driver](automation/test-execution/mutation-driver.txt)
are retained in the [automation directory](automation/test-execution/).
Transcripts and JUnit logs trim trailing whitespace only; every parameter name
and outcome is preserved and verified after normalization.
The [mutation manifest](automation/test-execution/mutation-manifest.json) verifies
byte-identical restoration of both helpers after the experiments. Their shared
SHA-256 remains `704ce62c2b3d0470476571d3703799b8c9aac73a74ed7a0e61ea772fdd6f749a`.

## Focused validation

The [final suite output](automation/test-execution/coverage-after.txt) and
[JUnit](automation/test-execution/suite-green.xml) record **200 passed**, with
zero failures or skips. The retained command is:

```text
env -u GITHUB_OUTPUT -u GITHUB_STEP_SUMMARY python3 -m pytest \
  tests/scripts/test_check_deliberate_break.py -q -m "not slow" \
  --cov=scripts.check_deliberate_break --cov-report=term-missing \
  --cov-report=json:docs/evidence/issue-3743/automation/test-execution/coverage-after.json \
  --junitxml=docs/evidence/issue-3743/automation/test-execution/suite-green.xml
```

Focused helper coverage remains **90.71%** before/after: statements **91.41%**
(532/582), branches **89.15%** (230/258). The
[before measurement](automation/test-execution/coverage-before.txt) records 197
passes and one pre-existing CLI failure: inherited `GITHUB_OUTPUT` points to a
read-only runner path. Removing that destination and `GITHUB_STEP_SUMMARY`
permits the complete final run without changing or skipping any test. Both
coverage JSON files are retained. These are focused measurements, not a new
whole-repository result.

[Checks](automation/test-execution/checks.txt) pass template sync/completeness,
focused Black/Ruff, whitespace validation and helper byte identity. Stock
repository-wide Black fails while creating its sandbox worker socket; the
[stock traceback](automation/test-execution/black-all.txt) is retained.
The previously retained [serial dispatch adapter](automation/black-serial-dispatch.txt)
calls Black's unchanged formatting/check routines and passes all 661 files with
the required options, as recorded in the [serial result](automation/test-execution/black-serial.txt).

## Verified local acceptance and handoff

- [ ] Run and retain the literal Anaconda-interpreter acceptance command on a runner where that interpreter exists.
- [x] Both helpers reject the real collection dependency defect, retain both streams, and fail against the prior implementation.
- [x] Both helpers reject pytest exits 2/3/4/5 and preserve genuine in-test import failures; each parameter has retained RED/GREEN evidence.
- [x] Template validation, focused formatting/lint, whitespace checks and helper byte identity pass.

The original checkout's Git metadata is read-only. This round uses a separate
writable Git directory at `/tmp/workflows-test-execution-3775.git` for the focused
source/evidence commit and `/tmp/workflows-test-execution-3775.bundle` for handoff.
Remote publication and checklist reconciliation must be confirmed by the owning
keepalive lane before calling these results remote-head validation.

The GitHub tools rejected both the blocker comment and `needs-human` label:
each write requires approval while this run's approval policy is `never`.
No remote checklist, comment or label was changed. The pending interpreter
criterion remains unchecked.
