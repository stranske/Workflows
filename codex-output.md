Made retry delays derive from a configurable max-retries/base-delay fallback so the verifier retry loop is explicit and still defaults to 3 exponential attempts, and updated the PR checklist to reflect the verified retry behavior and tests. This keeps the retry/backoff logic in `.github/scripts/verifier_ci_query.js` clear and consistent with the acceptance criteria, while `.github/scripts/__tests__/verifier-ci-query.test.js` continues to validate success and exhaustion cases.

Tests run:
- `node --test .github/scripts/__tests__/verifier-ci-query.test.js`

Next steps:
1. Run the full selftest CI workflow to satisfy the remaining “Selftest CI passes” checkbox.
2. If you want broader local coverage, run `node --test .github/scripts/__tests__/*.test.js`.