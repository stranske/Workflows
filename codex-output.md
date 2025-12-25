Moved the keepalive post-work instruction persistence setup ahead of the early-sync return to avoid a runtime ReferenceError, added new test coverage for post-work cleanup/state transitions and merge-manager eligibility/label handling, and updated the task checklist to reflect verified work in `codex-prompt.md`. The keepalive fix lives in ` .github/scripts/keepalive_post_work.js`, while the new suites are in `.github/scripts/__tests__/keepalive-post-work.test.js` and `.github/scripts/__tests__/merge-manager.test.js` with checklist updates in `codex-prompt.md`.

Tests run:
- `node --test .github/scripts/__tests__/keepalive-post-work.test.js`
- `node --test .github/scripts/__tests__/merge-manager.test.js`
- `node --test .github/scripts/__tests__/*.test.js`

Next steps:
1. Run the `Selftest CI` workflow to confirm no regressions.