Implemented retry-backed CI querying so transient GitHub API failures no longer show up as “not found”, with clear error classification and logging. Updated `fetchWorkflowRun` to use an exponential backoff retry wrapper (1s/2s/4s, 3 retries) and surfaced `api_error` plus `error_category` in results to distinguish API errors from missing runs in `agents_verifier_context`. Added tests covering retry success and retry exhaustion.

Files touched:
- `.github/scripts/verifier_ci_query.js`
- `.github/scripts/__tests__/verifier-ci-query.test.js`

Tests:
- `node --test .github/scripts/__tests__/verifier-ci-query.test.js`

Next steps:
1. If you want a broader check, run the full JS test suite for `.github/scripts/__tests__`.
2. If you want the error_category displayed in other reports, I can update those consumers.