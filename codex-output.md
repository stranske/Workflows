Updated keepalive sweep logic to treat `agent:*` labels as CLI mode (no instruction comments) and defaulted target labels to `agents:keepalive`, then refreshed keepalive fixtures/tests and added a CLI-skip scenario. These changes live in `scripts/keepalive-runner.js` and the keepalive workflow fixtures/tests under `tests/workflows/fixtures/keepalive/` plus `tests/workflows/test_keepalive_workflow.py`.

- Tests: `pytest tests/workflows/test_keepalive_workflow.py`
- Commit: `0439872` “Suppress keepalive instructions for CLI agents”

Blockers/notes:
- Pipeline validation and GITHUB_STEP_SUMMARY changes are blocked by the workflow edit restriction (`.github/workflows/**`). A human will need to update those workflows.
- I see a pre-existing modification in `codex-prompt.md` that I didn’t touch—how would you like to handle it?

Next steps (pick one):
1) Have a human update the workflows to pass `agent_type`, skip gate summaries for CLI PRs, and emit `GITHUB_STEP_SUMMARY`.
2) Run the full CI to validate keepalive behavior across the suite.