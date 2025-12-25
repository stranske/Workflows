Added the initial error classification utility with recovery guidance and a focused unit test so we can start wiring classification into retries and keepalive logic. New logic lives in `.github/scripts/error_classifier.js`, with coverage in `.github/scripts/__tests__/error-classifier.test.js`.

Tests run:
- `node --test .github/scripts/__tests__/error-classifier.test.js`

Next steps:
1. Integrate `classifyError` into GitHub API retry/backoff wrappers (likely `.github/scripts/api-helpers.js`) and add retry logging.
2. Extend keepalive failure handling to record `error_type` and reset counters for transient errors.