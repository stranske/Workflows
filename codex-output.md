Added a merged-PR CI query test to exercise merge/head SHA fallback per workflow and updated the PR task checklist/progress to reflect completed work. The new coverage lives in `.github/scripts/__tests__/agents-verifier-context.test.js`, and the updated task tracking is in `codex-prompt.md`.

**Tests**
- `node --test .github/scripts/__tests__/agents-verifier-context.test.js`

Next steps:
1) Run the verifier against a real merged PR to confirm CI results are fetched as expected.
2) Validate the verifier no longer produces false negatives on post-merge runs.