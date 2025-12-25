Expanded the error classifier’s pattern coverage to better detect common transient/auth cases and added tests to verify ENOTFOUND and Unauthorized handling. This advances the “map common error patterns to categories” task in `.github/scripts/error_classifier.js` and `.github/scripts/__tests__/error-classifier.test.js`.

Tests:
- `node --test .github/scripts/__tests__/error-classifier.test.js`

Next steps (pick one):
1) Implement retry behavior tests in `.github/scripts/__tests__/github-api-retry.test.js` for additional transient codes.
2) Start on keepalive failure handling changes (state/error_type updates) in `.github/scripts/keepalive_*` scripts.