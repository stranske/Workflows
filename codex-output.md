Added a merge-commit-focused unit test to verify CI runs are selected for the merge SHA and updated the PR checklist to reflect completed CI-query/prompt work and the new verification test. This keeps the verifier context behavior validated while keeping task tracking accurate in `codex-prompt.md`.

Details
- New test in `.github/scripts/__tests__/agents-verifier-context.test.js` asserts merge-commit selection across workflows and confirms CI results match the merge SHA.
- Updated progress/checkboxes in `codex-prompt.md` to reflect completed Round 1/2/3 items, the new merged-PR test, and relevant acceptance criteria.

Tests
- `node --test .github/scripts/__tests__/verifier-ci-query.test.js .github/scripts/__tests__/agents-verifier-context.test.js`

Next steps
1. If you want full end-to-end validation, run the verifier against a merged PR to confirm live CI results and close the remaining “false negatives” verification task.