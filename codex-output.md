Added required Scope/Tasks/Acceptance fields to the Codex bug/feature issue forms so source issues always carry those sections, and added a test to enforce the requirement going forward. Updated the PR body checklist to reflect completion.

- Updated issue forms: `.github/ISSUE_TEMPLATE/bug_report_codex.yml`, `.github/ISSUE_TEMPLATE/feature_request_codex.yml`
- Added validation test: `tests/workflows/test_workflow_agents_consolidation.py`
- Checked off tasks: `codex-prompt.md`

Tests run:
- `python -m pytest tests/workflows/test_workflow_agents_consolidation.py`

Next step (optional): run the full test suite with `python -m pytest`.