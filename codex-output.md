Updated error classification to recognize error codes and request-timeout statuses, so transient failures are detected even when errors only expose a code field. Added a focused test to validate this behavior in the classifier suite.

Details:
- Extended message normalization in `.github/scripts/error_classifier.js` to include `error.code` and related response fields; added `408` to transient status classification.
- Added a test case in `.github/scripts/__tests__/error-classifier.test.js` to ensure `ETIMEDOUT` is classified as transient.

Tests:
- `node --test .github/scripts/__tests__/error-classifier.test.js`

If you want broader coverage, you could run the full Node test set:
1) `node --test .github/scripts/__tests__/error-classifier.test.js` (already ran)
2) `node --test .github/scripts/__tests__/*.test.js`