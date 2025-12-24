Handled inline comments in keepalive key/value config parsing so values like `autofix_enabled: true # ...` are interpreted correctly, and added a regression test for this edge case in `.github/scripts/__tests__/keepalive-loop.test.js` to cover the behavior in `.github/scripts/keepalive_loop.js`.

Tests run:
- `node --test .github/scripts/__tests__/keepalive-loop.test.js`

Next steps:
1) Run the full scripts test suite if you want broader coverage: `node --test .github/scripts/__tests__`