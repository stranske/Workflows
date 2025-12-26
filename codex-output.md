Added merge-manager coverage for CI label add/missing branches and updated the PR checklist/progress now that the JS suite was run. Changes are in `.github/scripts/__tests__/merge-manager.test.js` and `codex-prompt.md`.

Tests:
- `node --test .github/scripts/__tests__/*.test.js`

Next steps:
1. Decide whether any test documentation updates are needed and check off the task in `codex-prompt.md`.
2. Run/verify the `Selftest CI` workflow to satisfy the remaining acceptance item.