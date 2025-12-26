Added explicit CI-verification guidance in the verifier context and prompt so test validation relies on CI results, updated coverage in the verifier context test, and reconciled the PR checklist to reflect completed tasks. This keeps the verifier aligned with CI while retaining lightweight local checks.

Details:
- Added a CI verification note in ` .github/scripts/agents_verifier_context.js ` to instruct relying on CI results and avoiding local test reruns.
- Extended the verifier context test to assert the new guidance appears in the rendered context at ` .github/scripts/__tests__/agents-verifier-context.test.js `.
- Clarified verifier guidance text to forbid local test runs in ` .github/codex/prompts/verifier_acceptance_check.md `.
- Updated checklist progress and task status in ` codex-prompt.md ` to reflect verified work.

Tests:
- `node --test .github/scripts/__tests__/verifier-ci-query.test.js .github/scripts/__tests__/agents-verifier-context.test.js`

Next steps:
1) Run the verifier against a merged PR to confirm CI results are fetched as expected.