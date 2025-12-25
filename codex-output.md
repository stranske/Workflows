Added skip-history coverage for non‑gate failures and wired the test GitHub stub to expose `issues.listComments`, so the gate runner’s prior‑failure logic is exercised in `.github/scripts/__tests__/keepalive-orchestrator-gate-runner.test.js`. Updated the task progress tally in `codex-prompt.md` to reflect current completion.

Tests:
- `node --test .github/scripts/__tests__/keepalive-orchestrator-gate-runner.test.js`
- `node --test .github/scripts/__tests__/*.test.js`

Next steps:
1) Run Selftest CI to satisfy the regression criterion.
2) Confirm whether test documentation updates are needed; if not, check the remaining box in `codex-prompt.md`.