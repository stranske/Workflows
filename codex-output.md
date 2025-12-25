Added an error diagnostics helper that emits a sanitized JSON payload suitable for an artifact, and verified it with tests. Also reconciled the task checklist after reviewing prior changes so progress reflects the verified work in `codex-prompt.md`.

Details:
- New diagnostics helper with CLI + sanitization to avoid secret-bearing keys: `.github/scripts/error_diagnostics.js`
- Coverage for diagnostics collection and redaction behavior: `.github/scripts/__tests__/error-diagnostics.test.js`
- Task checklist and progress updated after verifying error handling work: `codex-prompt.md`

Tests:
- `node --test --test-reporter spec .github/scripts/__tests__/error-classifier.test.js .github/scripts/__tests__/github-api-retry.test.js .github/scripts/__tests__/keepalive-loop.test.js`
- `node --test --test-reporter spec .github/scripts/__tests__/error-diagnostics.test.js`

Next steps (blocked by workflow edit restrictions in `agent-standard`):
1. Add a step in `.github/workflows/reusable-codex-run.yml` to call `node .github/scripts/error_diagnostics.js --output error_diagnostics.json` and upload it as an artifact on failure.
2. Add the failure classification/conditional retry/summary steps in `.github/workflows/reusable-codex-run.yml` per the remaining unchecked tasks.