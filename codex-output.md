Added coverage for default CI workflow selection in the verifier CI query tests, then reconciled the PR checklist/progress to reflect completed Round 1–3 work plus merged-PR CI verification. Updates are in `.github/scripts/__tests__/verifier-ci-query.test.js` and the task list in `codex-prompt.md`.

Tests run:
- `node --test .github/scripts/__tests__/verifier-ci-query.test.js`
- `node --test .github/scripts/__tests__/agents-verifier-context.test.js`

Next steps:
1. Run the verifier on a real merged PR to confirm “Selftest CI passes” can be marked PASS from CI results.
2. Confirm no false negatives remain by comparing verifier output to CI on a recent merge.