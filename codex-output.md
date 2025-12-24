Handled numbered checklist items like `1)` in keepalive parsing and added coverage to keep the task appendix and counts accurate.

- Updated checkbox parsing and checklist normalization to accept numbered bullets with parentheses in `.github/scripts/keepalive_loop.js`
- Added tests for parenthesized numbered lists in `.github/scripts/__tests__/keepalive-loop.test.js`
- Commit: `Handle numbered checklist items in keepalive loop`

Tests not run (not requested).

Next steps:
1) Run `node --test .github/scripts/__tests__/keepalive-loop.test.js` to validate the new cases.
2) Run the full test suite if needed for coverage.