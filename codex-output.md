Updated the verifier context to render CI results as a compact markdown table, making the “CI Verification” section easier to scan, and aligned the context test with the new format in `.github/scripts/__tests__/agents-verifier-context.test.js`.

Tests: `node --test .github/scripts/__tests__/agents-verifier-context.test.js`

Note: `codex-prompt.md` is still modified from earlier work and wasn’t included in this commit.

Next steps (pick one):
1) Run the verifier on a merged PR to confirm CI results resolve as expected.
2) Run the full verifier-related test suite if you want broader coverage.