Added coverage for the CI query helper to verify latest-run selection when no target SHA is supplied, and updated the PR task checklist/acceptance criteria to reflect verified work in `codex-prompt.md`.

Details:
- Added a new test case in `.github/scripts/__tests__/verifier-ci-query.test.js` to assert the latest workflow run is used when `targetSha` is omitted.
- Marked completed tasks and acceptance criteria in `codex-prompt.md` now that the CI query logic, context integration, and prompt updates are verified.

Tests:
- `node --test .github/scripts/__tests__/verifier-ci-query.test.js`
- `node --test .github/scripts/__tests__/agents-verifier-context.test.js`

Next steps:
1) Exercise the verifier against a merged PR to confirm CI results are fetched as expected.
2) Confirm the verifier no longer reports false negatives from stale local test runs.