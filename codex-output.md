Added fork detection to verifier context so forked PRs are skipped with the same output hygiene as other skip cases, and added a unit test to cover the fork edge case. Changes are in `.github/scripts/agents_verifier_context.js` and `.github/scripts/__tests__/agents-verifier-context.test.js`.

Tests run:
- `node --test .github/scripts/__tests__/agents-verifier-context.test.js`

Note: `codex-prompt.md` is still modified in the working tree and I did not touch it. How would you like to handle that?

If you want, I can:
1) Run the full Node test suite: `node --test .github/scripts/__tests__/*.test.js`
2) Proceed to the next Keepalive task