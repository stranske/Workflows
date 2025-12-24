Updated the status summary builder to accept an `agentType` flag and suppress workflow clutter for CLI agents, plus added targeted tests and verified them. Pipeline validation and workflow wiring remain blocked here because they require external runs or edits under `.github/workflows/**` (restricted without `agent-high-privilege`).

Details
- CLI-agent suppression logic lives in `/.github/scripts/agents_pr_meta_update_body.js`, including agent type input resolution and conditional omission of head SHA/required checks/table.
- Tests added in `/.github/scripts/__tests__/agents-pr-meta-update-body.test.js` to cover both CLI and non-CLI output.
- Tests run: `node --test .github/scripts/__tests__/agents-pr-meta-update-body.test.js`

Blocked items
- Pipeline validation tasks require creating a real PR, label, and checking workflow logs.
- `GITHUB_STEP_SUMMARY` and agent-type plumbing in workflows need edits under `.github/workflows/**`, which I can’t modify in this run.

Next steps (pick one)
1. Approve workflow edits so I can wire `agent_type` into the update job and add the step summary output.
2. Have a human apply the workflow changes; I can then adjust scripts/tests if needed.
3. Create the test PR with `agent:codex` label and share logs so I can verify the pipeline validation tasks.