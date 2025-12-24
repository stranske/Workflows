Added edge-case coverage for keepalive state handling so malformed payloads, missing markers/comments, invalid inputs, and undefined merges are exercised, aligning the keepalive-state tests with the acceptance criteria. Updates are in `/.github/scripts/__tests__/keepalive-state.test.js` to cover parse/load behavior and inert manager defaults for invalid context.

Tests run:
- `node --test .github/scripts/__tests__/keepalive-state.test.js`

Suggestions:
1) Run the full scripts test suite: `node --test .github/scripts/__tests__`