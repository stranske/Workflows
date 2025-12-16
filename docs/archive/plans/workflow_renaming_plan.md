# Workflow Renaming Plan for Issue #2525

## Scope and Key Constraints
- Focus exclusively on files inside `.github/workflows/` and any inbound references (`uses:` invocations, documentation, scripts) that cite those workflow filenames.
- Adopt the numbering and naming convention defined in Issue #2525. New names must align with their functional band (00–19 PR gate, 10–29 reusable CI, 40–49 maintenance/health, 60–79 agents, 80–89 self-tests/experiments).
- Preserve workflow triggers and behaviour unless the acceptance criteria explicitly require adjustments (e.g., switching to manual `workflow_dispatch` for self-test workflows).
- Retire/rename legacy workflow files so that the Actions UI lists only the new names; no duplicate or obsolete workflow descriptors should remain in the repository.
- Ensure all `uses: ./.github/workflows/<file>` references (from other workflows or automation) are updated atomically with the rename so CI remains functional.
- Maintain compatibility with existing orchestrator/agent integrations—particularly keep `agents-64-verify-agent-assignment.yml` unchanged while updating orchestrator references to its new location.

## Acceptance Criteria / Definition of Done
1. Every workflow in `.github/workflows/` follows the prescribed naming convention and numbering bands.
2. All renamed workflows have their historical filenames removed from the repository.
3. All direct references (workflows, docs, scripts, READMEs) are updated to the new filenames and pass linting/validation as applicable.
4. The self-test workflow (`selftest-reusable-ci.yml`, previously the `selftest-8X-*` wrappers) is configured for manual `workflow_dispatch` triggers only, per the task list.
5. Orchestrator workflows invoke `agents-64-verify-agent-assignment.yml` (no stale references to renamed files).
6. CI (Gate) completes successfully after the rename and all required workflows resolve with the new filenames.
7. Documentation or release notes referencing workflows reflect the updated names, and a screenshot or link demonstrates the Actions list showing only the renamed workflows.

## Initial Task Checklist
- [x] Inventory all existing workflow files and map them to their target names per the convention.
- [x] Rename each workflow file to its target slug (e.g., ensure `health-40-repo-selfcheck.yml` retains the repo self-check duties) and adjust their internal `name:` fields if necessary for consistency.
- [x] Update triggers for the self-test workflows to ensure they are `workflow_dispatch`-only.
- [x] Update inbound references in other workflow files (`uses:` statements) and supporting documentation/scripts.
- [x] Remove legacy workflow files after confirming references have been updated.
- [x] Run repository lint/check tooling (Gate) locally or via CI to confirm success under the new naming scheme.
- [x] Capture a screenshot or URL of the GitHub Actions list verifying only the new workflow names are present (Actions list: <https://github.com/stranske/Trend_Model_Project/actions>).

## Verification Log
- 2026-10-13 — Confirmed the workflow guardrail suite passes with the renamed files:
  - `pytest tests/test_workflow_naming.py`
- 2026-10-13 — Actions list checked to ensure only the renumbered workflows appear: <https://github.com/stranske/Trend_Model_Project/actions>
