Adjusted CI conclusion normalization so completed runs without a conclusion are treated as `unknown`, preventing ambiguous “completed” statuses from being misread as pass/fail, and added coverage for that case in the CI query tests in `.github/scripts/verifier_ci_query.js` and `.github/scripts/__tests__/verifier-ci-query.test.js`.

Tests: `node --test .github/scripts/__tests__/verifier-ci-query.test.js`

Notes: `codex-prompt.md` is still modified from before; I left it untouched.