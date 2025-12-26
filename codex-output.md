Implemented a merge-then-head SHA fallback for CI lookup so PR-triggered workflows like Gate still resolve after merge, then updated the verifier context to pass the SHA list and expanded tests plus checklist reconciliation. Changes are in `.github/scripts/verifier_ci_query.js`, `.github/scripts/agents_verifier_context.js`, `.github/scripts/__tests__/verifier-ci-query.test.js`, `.github/scripts/__tests__/agents-verifier-context.test.js`, and `codex-prompt.md`.

Tests run:
- `node --test .github/scripts/__tests__/verifier-ci-query.test.js`
- `node --test .github/scripts/__tests__/agents-verifier-context.test.js`

Next steps:
1. Run the verifier on a real merged PR to confirm CI results resolve and “Selftest CI passes” can be marked PASS.
2. Compare verifier output to CI on a recent merge to confirm no false negatives remain.