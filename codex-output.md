Added missing unit coverage for the keepalive loop and verifier context logic, focusing on config parsing, decision branches, and skip/aggregation behavior that the PR needed to satisfy acceptance criteria. The new tests follow the existing `node:test` style in `.github/scripts/__tests__` and stub GitHub/core calls to keep them deterministic.

Details
- `./.github/scripts/__tests__/keepalive-loop.test.js` covers checkbox counting, config parsing variants, and the main action/reason paths for the keepalive loop.
- `./.github/scripts/__tests__/agents-verifier-context.test.js` covers skip conditions, base-branch mismatch handling, and context generation with linked issues.

Tests
- `node --test .github/scripts/__tests__/keepalive-loop.test.js .github/scripts/__tests__/agents-verifier-context.test.js`

Next steps (optional)
1) Run the full scripts test suite: `node --test .github/scripts/__tests__`