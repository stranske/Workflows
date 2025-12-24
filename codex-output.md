Expanded keepalive checkbox parsing to handle `*`, `+`, and numbered list task formats so task counts match common markdown patterns, and added a test to lock the new behavior in. Changes are in `.github/scripts/keepalive_loop.js` and `.github/scripts/__tests__/keepalive-loop.test.js`.

Tests run:
- `node --test .github/scripts/__tests__/keepalive-loop.test.js`

Next steps you may want:
1) Run the full Node test suite: `node --test .github/scripts/__tests__/*.test.js`
2) Check coverage thresholds if needed: `npm test`