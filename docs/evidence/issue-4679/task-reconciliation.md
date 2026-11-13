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
