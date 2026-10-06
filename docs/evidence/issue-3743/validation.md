# Archived-base pytest proof validation

This follow-up to PR #3775 replaces mocked base subprocess results with real
git/archive/pytest regressions in `tests/scripts/test_check_deliberate_break.py`.
Both the root and consumer helpers exercise missing collection dependencies,
diagnostics on either stream, pytest exits 2/3/4/5, and a missing import raised
inside a running test. The existing production guards pass these regressions;
no additional production change was justified.

The target remains the PR's escaped-defect selection. The PR records repository
coverage of 80.95% from Gate run 37409054404. This run measures only the named
helper; it does not establish new whole-repository coverage or a fleet target.

## Observed RED/GREEN proof

Every case runs actual subprocesses against a temporary committed repository.
The helper archives its base commit and overlays the candidate test file.
For stream tests, a committed pytest hook directs the terminal reporter to
stdout or stderr and emits independent sentinels on both streams. Exit tests
cause actual collection, internal, usage, or empty-selection outcomes. The
behavioral control imports an unavailable dependency inside the base function
called by the test body.

| Cases, across both helpers | Prior implementation | Import-classifier mutation | Restored helper |
| --- | --- | --- | --- |
| Missing collection dependency (2) | 2 fail with unexpected PASS | Not selected | 2 pass |
| Collection diagnostics on stdout/stderr (4) | 4 fail with unexpected PASS | Not selected | 4 pass |
| Actual pytest exits 2/3/4/5 (8) | 8 fail with unexpected PASS | Not selected | 8 pass |
| Missing import inside a running test (2) | 2 pass | 2 fail with unexpected FAIL_BROKEN | 2 pass |

The first experiment temporarily replaced both helper files with their exact
versions at `5656aa96fc0f4f2d0525d42c40c15694ca2c949d`. The second removed the
collection-evidence predicate from `_missing_module_from_pytest_output` in both
current copies. No test was modified between RED and GREEN. Both helpers were
restored byte-identically after each mutation. Their SHA-256 before and after is
`704ce62c2b3d0470476571d3703799b8c9aac73a74ed7a0e61ea772fdd6f749a`.

Commands, per-parameter outcomes, mutation diffs, and source/test hashes are
retained in the [automation evidence directory](automation/):
[prior implementation RED](automation/prior-implementation-red.txt),
[behavioral control RED](automation/in-test-import-red.txt),
[restored GREEN](automation/restored-green.txt), and the
[mutation manifest](automation/mutation-manifest.json).
Retained transcripts remove trailing whitespace only; all output lines and
outcomes remain present. Mutation diffs use zero context to avoid whitespace-only
context lines in the evidence files.

## Focused suite and coverage

Observed interpreter: `/opt/hostedtoolcache/Python/3.14.7/x64/bin/python3`.
The command was run before replacing the mocks and after restoring the helpers:

```text
python3 -m pytest tests/scripts/test_check_deliberate_break.py -q -m "not slow" \
  --cov=scripts.check_deliberate_break --cov-branch --cov-report=term-missing \
  --cov-report=json:<automation/coverage-before.json or coverage-after.json>
```

| Measurement | Before | After |
| --- | --- | --- |
| Tests passing (no failures/skips) | 191 | 198 |
| Combined focused coverage | 90.71% | 90.71% |
| Statement coverage | 91.41% (532/582) | 91.41% (532/582) |
| Branch coverage | 89.15% (230/258) | 89.15% (230/258) |

Full output and JSON measurements are retained as
[before](automation/coverage-before.txt) and [after](automation/coverage-after.txt).
The replacement tests strengthen subprocess integration evidence for branches
already covered by mocks, so the percentage is unchanged.

## Validation and remaining boundary

[Validation output](automation/checks.txt) records passing template sync,
template completeness, focused Black/Ruff, `git diff --check`, and helper
byte-identity checks. `docs/keepalive/GoalsAndPlumbing.md` already describes the
verified collection/execution boundary and the genuine in-test import control.

Inherited `GITHUB_OUTPUT` and `GITHUB_STEP_SUMMARY` pointed outside this sandbox's
writable roots, so local validation removes those output destinations. Stock
Black's parallel worker paths failed or hung here. The retained
[serial dispatch adapter](automation/black-serial-dispatch.txt) calls Black's
unchanged `reformat_one` formatter, validation, and reporting routines for every
selected file, preserving the CLI options and failure exit status.
The required [repository-wide formatting gate](automation/black-all.txt),
`black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .`,
passes with all 661 files unchanged using that adapter.

The literal `/opt/anaconda3/bin/python3 -m pytest
tests/scripts/test_check_deliberate_break.py -q` acceptance check remains pending:
that interpreter is absent in this runner. The
[launch attempt](automation/requested-interpreter.txt) records the missing path.
The available-interpreter results above do not claim to satisfy that exact-path
requirement.

The implementation tasks are verified locally:

- [x] Real git/archive regressions cover the unavailable dependency, both diagnostic streams, and exits 2/3/4/5.
- [x] The existing targeted `verify_spec` guards reject reproduced false PASS results and preserve behavioral RED.
- [x] Root/template helpers match byte-for-byte and the keepalive documentation describes the proof boundary.
- [x] Every parameter case has observed RED/GREEN evidence, byte-identical restoration, and before/after coverage.
- [ ] Repeat the literal Anaconda-interpreter acceptance command on a runner where that interpreter exists.

This sandbox also makes the original checkout's `.git` read-only. Local staging
and committing there failed with a read-only `index.lock` error. GitHub blob
creation was rejected because it requires approval while this run's approval
policy is `never`. The verified changes can be committed in an isolated writable
checkout and delivered as a Git bundle; remote publication and PR/issue checklist
updates remain unavailable in this run.
