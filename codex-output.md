Updated the verifier context expectations to include the new `error_category`/`error_message` fields emitted by `queryVerifierCiResults`, so the deep-equal assertions match the current output shape in `.github/scripts/__tests__/agents-verifier-context.test.js`.

Tests run:
- `node .github/scripts/__tests__/agents-verifier-context.test.js`

If you want, I can re-run the full suite with `node --test .github/scripts/__tests__/*.test.js`.