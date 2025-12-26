Added an `error_message` field to verifier CI results so API failures are explicit in the output, and updated tests plus the PR checklist to reflect the completed retry work.

- Emitted `error_message` for each workflow result (retry exhaustion includes attempt count) in `.github/scripts/verifier_ci_query.js`.
- Updated expected objects for retry/error scenarios in `.github/scripts/__tests__/verifier-ci-query.test.js`.
- Checked off completed tasks and acceptance items in `codex-prompt.md`.

Tests run:
- `node --test .github/scripts/__tests__/verifier-ci-query.test.js`

Next steps:
1. Trigger Selftest CI (or run the broader `.github/scripts/__tests__` suite) to clear the remaining “Selftest CI passes” checkbox.