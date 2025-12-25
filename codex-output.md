Added a keepalive gate test for missing required labels and updated the PR task checklist to reflect completed test work in `codex-prompt.md`. New coverage verifies the skip reason includes the missing label identifiers.

Tests run:
- `node --test .github/scripts/__tests__/keepalive-orchestrator-gate-runner.test.js`

Next steps:
1) Run the full test suite per the remaining task requirement.
2) Decide whether any test documentation updates are needed.