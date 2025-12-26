Added a new agents-guard test to assert non-`pull_request_target` events skip safety checks, and reconciled the PR checklist now that the round test files are verified. Updated `codex-prompt.md` to mark completed tasks and acceptance items based on the passing test run.

- Test change: ` .github/scripts/__tests__/agents-guard.test.js`
- PR body updates: `codex-prompt.md`

Tests:
- `node --test .github/scripts/__tests__/*.test.js`

Next steps:
1) Run the full repo test suite (if required by your CI policy) to cover the remaining checklist item.  
2) Decide whether any test documentation updates are still needed.