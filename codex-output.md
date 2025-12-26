Exposed CI results directly from the verifier context builder so callers can rely on the same CI data that’s written into the markdown, and added coverage to assert the new return shape in both skip and success paths. Updates are in `.github/scripts/agents_verifier_context.js` and `.github/scripts/__tests__/agents-verifier-context.test.js`.

Tests: `node --test .github/scripts/__tests__/agents-verifier-context.test.js`

Note: `codex-prompt.md` is modified in your working tree already; I didn’t touch it.

If you want, I can also:
1) Run the remaining verifier-related tests (`node --test .github/scripts/__tests__/verifier-ci-query.test.js`).
2) Update the task checklist in `codex-prompt.md` after any additional verification you want to do.