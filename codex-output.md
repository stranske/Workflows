Added a CI query test that covers workflowId/workflowName aliases and updated the task checklist to reflect verified CI integration and prompt guidance. The new coverage lives in `.github/scripts/__tests__/verifier-ci-query.test.js`, and progress updates are in `codex-prompt.md`.

- Tests run: `node --test .github/scripts/__tests__/verifier-ci-query.test.js`, `node --test .github/scripts/__tests__/agents-verifier-context.test.js`, `node --test .github/scripts/__tests__/verifier-acceptance-prompt.test.js`
- Commit: `Add CI query alias test`

Next steps:
1) Run the verifier against a real merged PR to validate CI result fetching end-to-end and confirm “Selftest CI passes” can be marked PASS.
2) Validate that post-merge verification no longer creates false negatives in a recent merged PR.