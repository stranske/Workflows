Added a GitHub API retry helper with transient error classification, backoff + jitter, rate-limit header handling, and per-operation retry limits, plus tests for retry behavior. Updated the PR task checkboxes to reflect the completed retry and error-classification subtasks in `codex-prompt.md`.

Details and context:
- New retry module in `.github/scripts/github_api_retry.js` builds on the existing error classifier and backoff helper to decide when to retry and how long to wait.
- Tests added in `.github/scripts/__tests__/github-api-retry.test.js` cover retry delays (including Retry-After and rate-limit reset) and transient/non-transient behavior.
- Task checklist updates in `codex-prompt.md`.

Tests:
- `node --test .github/scripts/__tests__/error-classifier.test.js`
- `node --test .github/scripts/__tests__/github-api-retry.test.js`

Next steps (pick one):
1) If we need to proceed with “Update `reusable-codex-run.yml`…”, I’ll need `agent-high-privilege` approval to edit `.github/workflows/*`.
2) Implement the keepalive loop failure-handling updates (no workflow edits required).