Added agent-type inference from PR labels so the PR meta updater can hide CLI-only status clutter even when the workflow doesn’t pass an explicit agent type, and captured this in new unit tests. Updated the task appendix checkboxes and progress line now that the step-summary work and conditional status summary behavior have been verified by tests in this repo.

Details:
- ` .github/scripts/agents_pr_meta_update_body.js` now resolves `agentType` from inputs/env or `agent:*` labels on the PR.
- ` .github/scripts/__tests__/agents-pr-meta-update-body.test.js` adds coverage for the new agent-type resolution logic.
- ` codex-prompt.md` marks the GITHUB_STEP_SUMMARY and conditional status summary items complete and updates progress.

Tests:
- `node --test .github/scripts/__tests__/agents-pr-meta-update-body.test.js`
- `node --test .github/scripts/__tests__/keepalive-loop.test.js`

Next steps:
1) Run the pipeline validation checklist by creating a test PR with `agent:codex` and verifying prompt/task appendix + iteration updates.
2) If you want the remaining workflow-dependent tasks done, run with `agent-high-privilege` to update `.github/workflows/agents-keepalive-loop.yml` and `.github/workflows/agents-pr-meta-v4.yml` (agent_type output + gate-summary suppression).