Updated the verifier CI query to fall back to API `url` when `html_url` is missing, added coverage for that path, and reconciled the task checklist/progress after running the verifier script tests. Changes are in `.github/scripts/verifier_ci_query.js`, `.github/scripts/__tests__/verifier-ci-query.test.js`, and `codex-prompt.md`.

Tests:
- `node --test .github/scripts/__tests__/*.test.js`

Next steps:
1) Run the verifier workflow against an actual merged PR to confirm CI results are pulled from live runs (needed to fully close “no false negatives” and the remaining acceptance criteria).