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
