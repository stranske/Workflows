Added the missing Scope/Tasks/Acceptance criteria sections to the agent task issue form and aligned the legacy agent task template with the required section headers so new issues match the format guide. Changes are in `.github/ISSUE_TEMPLATE/agent_task.yml` and `.github/ISSUE_TEMPLATE/agent-task.md`.

Tests:
- `python -m pytest` (timed out at 120s; first failure in `tests/test_integration_repo_template.py` due to pip needing network access)
- `python -m pytest tests/test_integration_repo_template.py -q` (failed: pip install of `setuptools>=64` could not reach the network)

I also see unrelated working tree changes: modified `codex-prompt.md` and untracked `keepalive-metrics.ndjson`. I didn’t create these intentionally—how would you like to proceed with them?

Next steps:
1. Tell me whether to keep, remove, or ignore `codex-prompt.md` and `keepalive-metrics.ndjson`.
2. Re-run `python -m pytest` in an environment with package index access, or I can try the test again with cached deps if available.