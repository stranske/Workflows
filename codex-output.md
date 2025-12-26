Extended guard coverage by adding safe-workflow and read-failure tests in `.github/scripts/__tests__/agents-guard.test.js`, then updated the PR checklist/acceptance tracking in `codex-prompt.md` after verifying all new tests pass and reviewing docs (no doc updates needed).

Tests run:
- `node --test .github/scripts/__tests__/*.test.js`

Next steps:
1. Run the repo’s Selftest CI workflow (or equivalent full CI) to satisfy the remaining “no regressions” acceptance item.