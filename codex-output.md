Added a keepalive gate runner test for the retry-cap path so prior skip history triggers `too-many-failures`, and reconciled the PR checklist after confirming tests and docs. Updates are in `.github/scripts/__tests__/keepalive-orchestrator-gate-runner.test.js` (new retry-cap coverage) and `codex-prompt.md` (task/acceptance checkbox updates after verifying tests and reviewing `.github/scripts/README.md`).

Tests run:
- `node --test .github/scripts/__tests__/*.test.js`

Next steps:
1. Run the `Selftest CI` workflow to satisfy the remaining acceptance criterion.