# Issue #4679 task reconciliation

Reviewed commits `5dd8c6af`, `8517a39c`, and `89e4390b` before continuing.
The unchecked implementation tasks duplicate completed work in those commits.

- [x] Preserve the authored command separately from the normalized executable command.
- [x] Serialize authored commands in execution and setup-failure results and match both forms in the renderer.
- [x] Cover failed gates for `/opt/anaconda3/bin/python` and `python3.11` in source and consumer templates.
- [x] Verify the regression rejects the deliberately broken renderer and passes after restoration.
- [ ] Both full source-fix test gates pass.
- [ ] Post-merge consumer sync and review verification succeeds (maintainer or automation follow-up).

The PR-body update, blocker comment, and `needs-human` label were blocked: the GitHub tools require approval, while this run's approval policy is `never`.

## Current-round validation

The regression now also checks a criterion containing a passing companion gate.
A failed normalized gate must still uncheck that criterion and report `1/2 passed`.

- `python3 -m pytest -q tests/workflows/test_acceptance_gate.py -m 'not slow'`: 63 passed.
- `node --test .github/scripts/__tests__/keepalive-loop.test.js`: passed.
- `ruff check tests/workflows/test_acceptance_gate.py`: passed.
- `black --check --line-length 100 tests/workflows/test_acceptance_gate.py`: passed.
- Isolated copies of both renderers with authored-command matching removed: four companion-gate cases failed; restoring matching made all four pass. Tracked renderers were unchanged during this experiment.
- `node --test .github/scripts/__tests__/*.test.js`: 142 test files passed, nine failed, including `spawnSync python3 EPERM` errors.
- `python3 -m pytest -q tests/ -m 'not slow'`: 46,282 passed, 83 failed, 25 skipped, 10 deselected, three xfailed, and five subtests passed in 1,534.52 seconds. No acceptance-gate tests are listed among the failures. The full source-fix gate remains incomplete.
- Black formatted the changed Python file. The required repository-wide check failed on a prohibited multiprocessing socket. With `BLACK_NUM_WORKERS=1`, it stalled in a formatter worker; a bounded stack diagnostic confirmed the wait, and the stalled checks were interrupted. The repository-wide formatting gate remains unverified.

## Delivery blockers

`git add` failed with `Read-only file system` while creating `.git/index.lock`.
No commit was created. The source/test patch is also saved at
`/tmp/issue-4679-companion-gate.patch`.

## Setup-failure follow-up

Extended the preparation-failure regression to verify serialized venv/install
failures uncheck the authored criterion for both interpreter forms through both
source and consumer-template renderers. Manual-only criteria stay checked.

- `python3 -m pytest -q tests/workflows/test_acceptance_gate.py -m 'not slow'`: 69 passed.
- `python3 -m pytest -q tests/workflows/test_acceptance_gate.py -k preparation_failure -m 'not slow'`: 8 passed, 61 deselected.
- Mutation check in isolated renderer copies: removing authored-command matching
  produced 8 failed cases; restoring it produced 8 passed cases. Tracked renderers
  were unchanged.
- `node --test .github/scripts/__tests__/keepalive-loop.test.js`: passed.
- `ruff check tests/workflows/test_acceptance_gate.py` and
  `black --check --line-length 100 tests/workflows/test_acceptance_gate.py`: passed.
- `node --test .github/scripts/__tests__/*.test.js`: 142 test files passed,
  9 failed, including `spawnSync python3 EPERM` errors. The full-source acceptance
  criterion remains unchecked.
- The full Python source gate was started with `-m 'not slow'` and interrupted
  after the read-only Git and formatting blockers were confirmed. It did not
  establish a passing full-suite result.
- The required repository-wide Black command again failed with a denied
  multiprocessing socket. A single-worker diagnostic timed out while waiting for
  a formatter worker; repository-wide formatting remains unverified.

`git add -- tests/workflows/test_acceptance_gate.py` again failed because
`.git/index.lock` cannot be created on a read-only filesystem. No commit was
created; the patch is saved at `/tmp/issue-4679-setup-failure.patch`.
Both the requested blocker comment and `needs-human` label were rejected because
the GitHub write tools require approval and the run's approval policy is `never`.
PR #4680 was verified open with `draft=false`. Live consumer sync and review
verification remain post-merge maintainer or automation work.

## Authored criteria with identical normalized commands

Reviewed commits `5dd8c6af` through `b0d7fde3`. The duplicate unchecked source,
serialization, renderer, and regression tasks describe implemented work. Verified
the existing implementation again before attempting PR-body reconciliation.

Added four JavaScript regression cases: two authored criteria normalize to the
same executable command but have different results. Each case verifies that only
the failing criterion is unchecked, the passing and manual criteria remain
checked, and the report remains `1/2 passed`. Both source and consumer renderers
are exercised, with each criterion taking a turn as the passing gate.

- `python3 -m pytest -q tests/workflows/test_acceptance_gate.py -m 'not slow'`: 69 passed.
- `node --test --test-isolation=none --test-name-pattern='normalized gate' .github/scripts/__tests__/keepalive-loop.test.js`: 16 passed.
- Isolated renderer copies with authored matching removed: all four new cases failed. Restoring matching: all four passed. Tracked renderer contents remained unchanged.
- `node --test .github/scripts/__tests__/*.test.js`: 142 test files passed, nine failed, including `spawnSync python3 EPERM` errors. Same failure inventory before and after the test change.
- `python3 -m pytest -q tests/ -m 'not slow'`: interrupted after the combined full-source gate and delivery were blocked; no complete result established.
- `git diff --check`: passed. This round changes no Python files.

The full-source and post-merge live-verification checkboxes remain unchecked.
PR-body reconciliation, the blocker comment, and the `needs-human` label were
rejected because GitHub write tools require approval and approval policy is
`never`. The reconciled body is saved at
`/tmp/issue-4679-reconciled-pr-body.md`.

`git add` failed creating `.git/index.lock` on the read-only filesystem, so no
commit was created. The test patch is saved at
`/tmp/issue-4679-authored-criteria.patch`. No protected workflows or generated
consumer PRs were changed.

## Shared-criterion result identity follow-up

Reviewed the six implementation/test commits through `a9e3a976`. The duplicated
unchecked source and regression tasks are already implemented and verified.
PR-body reconciliation was attempted before further changes, but the GitHub write
tool requires approval and this run's approval policy is `never`. The reconciled
body is saved at `/tmp/issue-4679-current-pr-body.md`.

Added eight source/template regressions for two authored commands in one criterion
that normalize to the same executable command. A passing result previously masked
the other command's failed or missing result, leaving the checkbox checked and
incorrectly allowing completion. Shared authored-command lookup now keeps the
completion decision, failure prompt, checkbox reconciliation and report consistent.
Results without authored-command metadata retain the legacy matching behavior.

- New renderer regression before the fix: 8 failed.
- New cached-plan regression before the completion fix: 8 failed (`2 != 1`).
- `node --test --test-isolation=none .github/scripts/__tests__/keepalive-loop.test.js`: 250 passed after the fixes.
- `python3 -m pytest -q tests/workflows/test_acceptance_gate.py -m 'not slow'`: 69 passed.
- Source/template renderer byte comparison, JavaScript syntax and `git diff --check`: passed.
- `node --test .github/scripts/__tests__/*.test.js` on the final patch: 142 test
  files passed, 9 failed, including `spawnSync python3 EPERM`. Same failure-file
  inventory as the pre-change run; the keepalive test file passes.
- No Python files changed; the Python formatting gate does not apply this round.
- The full Python gate was started with `-m 'not slow'` and interrupted after the
  delivery/full-source blockers were confirmed. It did not establish a complete result.

`git add` failed creating `.git/index.lock` on the read-only filesystem, so no
commit was created. GitHub rejected the PR-body update, blocker comment and
`needs-human` label because writes require approval under policy `never`.
PR #4680 was verified open with `draft=false`. Full-source and live-verification
criteria remain unchecked; consumer regeneration/review verification remains
post-merge maintainer or automation work.

## Real CLI publication follow-up

Extended the existing CLI publication test with the two reported interpreter
forms, each with passing and failing pytest gates. The test verifies authored
command metadata in extractor and execution JSON, publication through
`markAgentRunning`, checkbox reconciliation, persisted results, and cached-plan
reuse. This adds four cases alongside the existing two npm controls.

- `node --test --test-isolation=none .github/scripts/__tests__/keepalive-loop.test.js`: 254 passed.
- `python3 -m pytest -q tests/workflows/test_acceptance_gate.py -m 'not slow'`: 69 passed.
- Isolated renderer mutation removing authored-command matching: the two new
  failing-Python-gate cases failed; four controls passed. Restoring matching:
  all six publication cases passed. Tracked source files were never mutated.
- `node --test .github/scripts/__tests__/*.test.js` on the final patch: 142 test
  files passed, nine failed. The failure-file inventory matches the pre-edit
  baseline, including `spawnSync python3 EPERM` errors.
- `python3 -m pytest -q tests/ -m 'not slow'` was interrupted after the combined
  full-source gate and delivery were blocked; no complete Python result is claimed.
- JavaScript syntax validation and `git diff --check`: passed. No Python files changed.

`git add` failed because `.git/index.lock` cannot be created on the read-only
filesystem. No commit was created; the test patch is saved at
`/tmp/issue-4679-cli-publishing.patch`. GitHub rejected the PR-body reconciliation,
blocker comment and `needs-human` label because write tools require approval and
the approval policy is `never`. PR #4680 was verified open with `draft=false`.
Full-source and post-merge consumer verification criteria remain unchecked.

## Execution-error identity follow-up

Verified the duplicated source/serialization/renderer tasks against the existing
implementation. Added eight Python regression cases for timed-out gates (exit
124) and missing executables (exit 127). Both reported interpreter forms and
both source/template surfaces retain authored-command metadata through real
execution errors and JSON serialization. The renderer unchecks the authored
criterion, preserves the manual criterion, and reports `0/1 passed`.

- `python3 -m pytest -q tests/workflows/test_acceptance_gate.py -m 'not slow'`: 77 passed.
- `node --test --test-isolation=none .github/scripts/__tests__/keepalive-loop.test.js`: 254 passed.
- Isolated renderer copies with authored-command matching removed: all eight
  execution-error cases failed on the checked acceptance criterion. Restoring
  matching: all eight passed. Tracked renderers were unchanged.
- `black --line-length 100 tests/workflows/test_acceptance_gate.py`, the
  changed-file Black check, Ruff, source/template byte comparisons, and
  `git diff --check`: passed.
- Required repository-wide Black check: failed with `PermissionError` while
  binding a multiprocessing socket. A `BLACK_NUM_WORKERS=1` retry timed out
  after 60 seconds. Repository-wide formatting remains unverified.
- `node --test .github/scripts/__tests__/*.test.js`: 142 test files passed,
  nine failed, including `spawnSync python3 EPERM` errors.
- The full Python gate ran with `-m 'not slow'` and was interrupted after the
  delivery/full-source blockers were established. No passing result is claimed.

`git add` failed because `.git/index.lock` cannot be created on the read-only
filesystem. No commit was created, and the failed formatting gate also prohibits
committing Python changes. The test patch is saved at
`/tmp/issue-4679-execution-errors.patch`.

GitHub rejected the verified-checkbox update, blocker comment, and `needs-human`
label because writes require approval under policy `never`. The proposed PR
body is saved at `/tmp/issue-4679-execution-errors-pr-body.md`. PR #4680 was
verified open with `draft=false`. Full-source and post-merge consumer verification
criteria remain unchecked. No protected workflows or generated consumer PRs
were changed.

## Bare and pinned interpreter result identity

The implementation tasks are already present. A remaining matching defect let an
explicit `original_command: null` result from a bare `python3` gate stand in for
a pinned interpreter gate with the same normalized command and criterion. That
could hide a failed or missing result and incorrectly report completion.

Source and consumer-template lookup now distinguish explicit null metadata from
older results that omit the field. Expanded shared-criterion tests cover both
reported pinned interpreter forms paired with bare `python3`, both command
orders, and failed or missing results.

- Before the fix, the expanded regression had 16 failures among 40 cases.
- After the fix, `node --test --test-isolation=none .github/scripts/__tests__/keepalive-loop.test.js`: 286 passed.
- `python3 -m pytest -q tests/workflows/test_acceptance_gate.py -m 'not slow'`: 77 passed in 189.87 seconds.
- `node --test .github/scripts/__tests__/*.test.js`: 142 test files passed,
  nine failed before and after the change, with identical failing-file inventories,
  including `spawnSync python3 EPERM` errors. Full-source acceptance remains unchecked.
- The full Python gate with `-m 'not slow'` was interrupted after delivery and
  combined full-source validation were blocked; no complete passing result is claimed.
- JavaScript syntax, source/template byte comparison and `git diff --check`: passed.
  No Python files changed, so the Python formatting gate does not apply this round.

`git add` failed because `.git/index.lock` cannot be created on the read-only
filesystem. No commit was created. The code/test patch is saved at
`/tmp/issue-4679-bare-pinned-identity.patch`.
GitHub rejected the PR update, blocker comment and `needs-human` label because
writes require approval under policy `never`. PR #4680 was verified open with
`draft=false`. Post-merge consumer regeneration and review verification remain
maintainer or automation work; no protected workflows or generated consumer PRs
were changed.

## Authored interpreter edits invalidate cached success

Reviewed the six recent commits through `a5448af6`. The duplicated source,
serialization, renderer and regression tasks are already implemented. Attempted
to reconcile their PR checkboxes before proceeding; GitHub rejected the update
because write tools require approval under policy `never`.

Added four JavaScript regression cases covering both source/template renderers
and both directions of an authored interpreter edit. With the head and normalized
command unchanged, editing the authored interpreter must discard cached success,
uncheck the new criterion, preserve manual criteria and report `0/1 passed`.
The unchanged criterion first proves that the cached success is reusable.

- `node --test --test-isolation=none .github/scripts/__tests__/keepalive-loop.test.js`: 290 passed.
- `python3 -m pytest -q tests/workflows/test_acceptance_gate.py -m 'not slow'`: 77 passed in 135.76 seconds.
- Isolated renderer copies with authored-command matching removed: all four new
  cases failed. Restored matching: all four passed. Tracked renderers were unchanged.
- `node --test .github/scripts/__tests__/*.test.js`: 142 test files passed and
  nine failed before and after the edit, with identical failing-file inventories,
  including `spawnSync python3 EPERM` errors.
- The full Python gate with `-m 'not slow'` was interrupted after the full-source
  and delivery blockers were confirmed; no complete passing result is claimed.
- JavaScript syntax and `git diff --check`: passed. No Python files changed.

`git add` failed because `.git/index.lock` cannot be created on the read-only
filesystem, so no commit was created. The test patch is saved at
`/tmp/issue-4679-authored-interpreter-edit.patch`. GitHub also rejected the blocker
comment and `needs-human` label because writes require approval under policy
`never`. PR #4680 was verified open with `draft=false`. The full-source and live
consumer-verification checkboxes remain incomplete. No protected workflows or
generated consumer PRs were changed.
