Added coverage for keepalive instruction template generation/caching and updated the checklist to reflect verified Round 1/2 work plus the new template test. The new tests live in `.github/scripts/__tests__/keepalive-instruction-template.test.js` and validate template reads, cache resets, mention formatting, and fallback behavior; checklist progress is updated in `codex-prompt.md`.

- Tests: `node --test .github/scripts/__tests__/*.test.js`
- Commit: `test: cover keepalive instruction template`

Next steps:
1. Add `keepalive-post-work.test.js` coverage for cleanup/state transitions.
2. Add `merge-manager.test.js` coverage for merge eligibility/conflict/squash behavior.