Expanded verifier CI retry coverage so transient status codes 429/500/502/503/504 are all exercised with max-retry exhaustion checks, keeping the API-error path explicit in results. This is in `.github/scripts/__tests__/verifier-ci-query.test.js`.

Tests run:
- `node --test .github/scripts/__tests__/verifier-ci-query.test.js`

Notes:
- Set repo-local git identity to `codex <codex@users.noreply.github.com>` to complete the commit.

Next steps (optional):
1. Run the full JS test suite if you want broader verification.