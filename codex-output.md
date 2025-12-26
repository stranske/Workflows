Updated verifier guidance to explicitly require marking test-related criteria NOT MET when CI evidence is missing, and tightened the prompt test to enforce the new instruction. I also reconciled the task checklist and acceptance criteria in `codex-prompt.md` to reflect the verified CI integration work.

Tests:
- `node --test .github/scripts/__tests__/verifier-acceptance-prompt.test.js .github/scripts/__tests__/verifier-ci-query.test.js .github/scripts/__tests__/agents-verifier-context.test.js`