Added a new agents-guard coverage case to ensure team-only CODEOWNERS don’t bypass approval checks, and reconciled the PR checklist to reflect verified work and the latest full test run. Updates are in `.github/scripts/__tests__/agents-guard.test.js` and `codex-prompt.md`.

Tests run:
- `node --test .github/scripts/__tests__/*.test.js`

Next steps:
1. Run the `Selftest CI` workflow to confirm no regressions in existing tests.
2. Decide whether test documentation needs updates; if yes, point me to the expected doc location.