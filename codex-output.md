Added a verifier-context test to cover CI fallback from merge SHA to head SHA and updated the task checklist to reflect completed work in `codex-prompt.md`.

- Updated test helper to allow custom workflow-run responses and added a merged-PR fallback test in `.github/scripts/__tests__/agents-verifier-context.test.js`.
- Reconciled task and acceptance checkboxes in `codex-prompt.md` after verifying tests.

Tests run:
- `node --test .github/scripts/__tests__/agents-verifier-context.test.js .github/scripts/__tests__/verifier-ci-query.test.js`

Next steps:
1. Validate on a real merged PR run to confirm CI results appear in the verifier context.
2. Confirm the verifier no longer flags stale local test failures and then check the final remaining task/acceptance boxes.