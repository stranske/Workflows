Added new test coverage for guard logic: `agents-guard` now has label/approval/immutability checks, and `keepalive_guard_utils` has gate reason + skip history coverage. Changes live in `.github/scripts/__tests__/agents-guard.test.js` and `.github/scripts/__tests__/keepalive-guard-utils.test.js` to match existing Node test patterns and exercise the core decision branches.

- Tests run: `node --test .github/scripts/__tests__/agents-guard.test.js .github/scripts/__tests__/keepalive-guard-utils.test.js`
- Commit: `Add guard utils tests` (local git user set to `Codex <codex@local>`)

I also noticed `codex-prompt.md` is modified in the worktree; I didn’t touch it. How would you like to handle that file?

Next steps:
1. Proceed to Round 2 tests (`agents-pr-meta-orchestrator` and `keepalive-orchestrator-gate-runner`).
2. Run the full suite once all 7 new test files are added.