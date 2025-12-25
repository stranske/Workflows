Updated retry/backoff coverage with deterministic jitter tests and added retry log context assertions, then reconciled the PR task list to reflect verified items. Changes are in `.github/scripts/__tests__/api-helpers.test.js`, `.github/scripts/__tests__/github-api-retry.test.js`, and `codex-prompt.md`.

Tests run:
- `node --test .github/scripts/__tests__/api-helpers.test.js`
- `node --test .github/scripts/__tests__/github-api-retry.test.js`

Next steps (pick one):
1. Proceed to the next unchecked task and implement failure handling updates in non-workflow code.
2. Decide how you want to handle workflow updates in `.github/workflows/**` since they require `agent-high-privilege`.