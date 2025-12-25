Added coverage to validate that each error category returns the expected recovery guidance, tightening the error-classifier acceptance criteria in `.github/scripts/__tests__/error-classifier.test.js`.

Tests run:
- `node --test .github/scripts/__tests__/error-classifier.test.js`

Note: the remaining acceptance item about creating the error diagnostics artifact requires edits to `.github/workflows/reusable-codex-run.yml`, which is a protected workflow file and needs an `agent-high-privilege` run. If you want me to proceed, please handle that change or enable the higher-privilege environment.

Next steps:
1. If you want the workflow artifact creation implemented, grant `agent-high-privilege` and I’ll update `.github/workflows/reusable-codex-run.yml`.
2. Optionally run the full keepalive JS test suite.