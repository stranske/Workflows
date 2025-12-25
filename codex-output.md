Expanded error classification coverage and pulled nested API error details into the classifier to improve category detection and recovery guidance. Added a test to lock in the nested error parsing behavior in `.github/scripts/__tests__/error-classifier.test.js`.

- Updated patterns and status handling in `.github/scripts/error_classifier.js` for transient/auth/resource/logic detection.
- Added nested API error inspection test in `.github/scripts/__tests__/error-classifier.test.js`.

Tests run:
- `node --test .github/scripts/__tests__/error-classifier.test.js`

Next steps you may want:
1. Implement retry jitter/backoff logging in `.github/scripts/github_api_retry.js`.
2. Add retry behavior tests with mocked failures.