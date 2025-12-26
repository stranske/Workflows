Added an edge-case test for keepalive guard utils to cover unrelated comments/malformed skip counts, and updated the PR task checklist after verifying the test suite. Changes are in `.github/scripts/__tests__/keepalive-guard-utils.test.js` and `codex-prompt.md`.

Tests run:
- `node --test .github/scripts/__tests__/*.test.js`

Next steps:
1) Trigger/confirm the `Selftest CI` workflow to satisfy the remaining “no regressions” acceptance item.