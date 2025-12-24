Trimmed the CLI-agent PR body status summary to only show the Scope/Tasks/Acceptance checklists, keeping workflow metadata (Head SHA / Latest Runs / Required / table) only for non-CLI agents. Updated the CLI-specific test expectation accordingly in `.github/scripts/__tests__/agents-pr-meta-update-body.test.js`.

Tests: `node --test .github/scripts/__tests__/agents-pr-meta-update-body.test.js`

Blockers
- Pipeline validation tasks require creating/running a PR and checking workflow logs; not doable from this workspace.
- GITHUB_STEP_SUMMARY changes, gate summary suppression, and passing `agent_type` from workflows require edits under `.github/workflows/**`, which are disallowed without `agent-high-privilege`.

Next steps if you want me to continue:
1) Run with `agent-high-privilege` so I can edit workflow files for the Step Summary + agent_type plumbing.
2) Provide a test PR/run context to verify the pipeline validation items.