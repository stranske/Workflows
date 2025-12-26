Added coverage to validate that the verifier context includes CI workflow results, so the “CI Verification” section is exercised with real-looking workflow data. The change is in `.github/scripts/__tests__/agents-verifier-context.test.js` where workflow runs are stubbed and the rendered context asserts Gate/Selftest/PR11 entries.

Tests:
- `node --test .github/scripts/__tests__/agents-verifier-context.test.js`

Note: `codex-prompt.md` is still modified in the worktree from before; I didn’t touch it.

Next step:
1) Run the full `.github/scripts/__tests__` suite if you want wider coverage.