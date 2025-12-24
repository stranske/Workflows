Added push-event skip coverage for verifier context so missing SHA and PR lookup failures are exercised.

Details
- Extended ` .github/scripts/__tests__/agents-verifier-context.test.js ` to simulate push events without SHA, with no associated PR, and with PR lookup errors; these assert the skip outputs and warnings.

Tests
- `node --test .github/scripts/__tests__/agents-verifier-context.test.js`

Next steps
1) Run the full agent script test suite if you want broader coverage: `node --test .github/scripts/__tests__/*.test.js`