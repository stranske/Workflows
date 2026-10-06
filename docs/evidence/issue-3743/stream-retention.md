# Base dependency diagnostic stream acceptance

The first unchecked acceptance criterion remains blocked: this runner does not
have `/opt/anaconda3/bin/python3`. The [literal launch attempt](automation/stream-retention/requested-interpreter.txt)
records that failure. No replacement interpreter is claimed to satisfy it.

The next criterion now has explicit assertions in the named regression itself.
`test_base_collection_failure_cannot_prove_a_deliberate_break` commits a pytest
session hook with independent stdout/stderr sentinels into the archived base.
It requires the missing-module diagnostic and both sentinels in their respective
result fields for both root and consumer helpers. This is a test-only change.

## Observed mutation proof

| Experiment, across both helpers | Failed | Passed |
| --- | ---: | ---: |
| Drop the base import-error result's stdout | 2 | 0 |
| Drop the base import-error result's stderr | 2 | 0 |
| Restore the prior false-PASS implementation | 14 | 2 |
| Misclassify a missing import inside a running test | 2 | 0 |
| Restore current helpers | 0 | 16 |

The stream mutations change only the corresponding result field. In particular,
the stderr experiment fails at the new sentinel assertion, demonstrating that
the previous combined-output check could not enforce this requirement.
The prior implementation's two passing cases are the genuine behavioral-failure
controls. Every selected parameter case has an observed failing source mutation
and a restored passing result. Actual subprocess pytest executions, per-case
JUnit results, zero-context mutation diffs, commands, exits, and source/test
hashes are retained in the [automation evidence directory](automation/stream-retention/).
See its [mutation manifest](automation/stream-retention/mutation-manifest.json).

Both helpers were restored byte-identically after every experiment. Their common
before/after SHA-256 is
`704ce62c2b3d0470476571d3703799b8c9aac73a74ed7a0e61ea772fdd6f749a`.

## Focused validation

The available interpreter is `/opt/hostedtoolcache/Python/3.14.7/x64/bin/python3`.
Before and after this test change, the following command passes all 198 tests
with no failures or skips:

```text
python3 -m pytest tests/scripts/test_check_deliberate_break.py -q -m "not slow" \
  --cov=scripts.check_deliberate_break --cov-branch --cov-report=term-missing \
  --cov-report=json:<coverage-before.json or coverage-after.json>
```

[Before output](automation/stream-retention/coverage-before.txt) and
[after output](automation/stream-retention/coverage-after.txt) retain the measured
helper row: combined focused coverage is 90.71% in both runs. Statement coverage
is 91.41% (532/582), and branch coverage is 89.15% (230/258). This test strengthens
an existing proof boundary; it does not measure whole-repository coverage.

[Checks](automation/stream-retention/checks.txt) pass template sync, template
completeness, focused Black/Ruff, `git diff --check`, and helper byte identity.
Stock repository-wide Black encounters a sandbox worker socket permission error;
the [serial Black result](automation/stream-retention/black-serial.txt) passes all
661 files using the previously retained
[adapter](automation/black-serial-dispatch.txt), which invokes Black's unchanged
formatter and validation routines. The
[stock failure](automation/stream-retention/black-all.txt) is retained separately.

## Verified local acceptance

- [ ] The literal Anaconda-interpreter command passes and its output is retained.
- [x] The named collection regression uses real git/archive/pytest for both helpers, retains the missing module and both base streams, and fails against prior code.
- [x] Pytest exits 2/3/4/5 are rejected, genuine in-test import failure remains behavioral RED, and each selected parameter has observed mutation/restoration logs.
- [x] Template validation, focused formatting/lint, whitespace checks, and helper byte identity pass.

The original checkout's Git metadata is read-only. A separate writable Git
directory under `/tmp/workflows-stream-retention-3775` supports the focused
source/evidence commit without changing that metadata. Publication to the PR
must be confirmed separately before treating these local results as remote-head
validation.

GitHub rejected source blob creation, the blocker comment, and the `needs-human`
label because each write tool requires approval while this run's approval policy
is `never`. No remote source, checklist, comment, or label update was made.
PR #3775 was reread afterward: it remains open with `isDraft=false`, at head
`41920a5ece70da8b6324c39dc20974e7eb4dc4b5`. The verified commit is retained in
`/tmp/workflows-stream-retention-3775.bundle` for publication by the owning lane.
