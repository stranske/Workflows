Captured CI query output in the verifier context and expanded tests to validate the new output plus merge-SHA targeting. Updated the checklist to reflect the verified CI-query work and prompt changes in `codex-prompt.md`.

Details:
- ` .github/scripts/agents_verifier_context.js` now sets `ci_results` on success and defaults it to `[]` when skipping, so downstream steps can rely on a consistent output.
- ` .github/scripts/__tests__/agents-verifier-context.test.js` asserts the `ci_results` output and verifies CI queries use the merge commit SHA.
- `codex-prompt.md` checkboxes updated after running tests and reviewing the completed tasks/criteria.

Tests:
- `node --test .github/scripts/__tests__/verifier-ci-query.test.js .github/scripts/__tests__/agents-verifier-context.test.js`

Next steps:
1. Run the verifier on a real merged PR to confirm CI results are fetched in production and the “no false negatives” item can be checked.