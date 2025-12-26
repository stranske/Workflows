Added a push-event test to verify the verifier queries CI using the merge commit SHA and returns expected workflow results, then reconciled the task checklist to reflect the completed CI-query/prompt/test work and acceptance criteria in `codex-prompt.md`.

Details
- Added a new push-event merge-commit test in `.github/scripts/__tests__/agents-verifier-context.test.js`.
- Updated task/acceptance checkboxes and progress in `codex-prompt.md`.

Tests
- `node --test .github/scripts/__tests__/agents-verifier-context.test.js .github/scripts/__tests__/verifier-ci-query.test.js`

Next steps
1. Run the verifier against a real merged PR to confirm no false negatives remain.