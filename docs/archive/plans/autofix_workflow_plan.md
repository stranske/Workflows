# Autofix Workflow Implementation Plan

## Scope
- Introduce a guarded `autofix:clean` GitHub Actions workflow that runs on pull requests.
- Limit automation to formatting with `ruff format` and a conservative, explicitly curated subset of Ruff autofix rules.
- Ensure the workflow can land changes automatically on same-repo branches while providing a follow-up PR for forks.
- Keep main CI behaviour unchanged aside from consuming any autofix edits when they are present.

## Key Constraints
- The workflow must only request the minimal permissions required (`contents: write`, `pull-requests: write`).
- Allowed Ruff fixes are restricted to `F401`, `F841`, and the safe `E1/E2/E3/E4/E7/W1/W2/W3` families to avoid surprising edits.
- Automation may not force-push or mutate contributor forks directly.
- Guard against autofix loops by detecting bot-authored commits with the configured prefix.

## Acceptance Criteria
- Workflow is named `autofix:clean` and triggers on `pull_request` events.
- Executes `ruff format .` followed by `ruff check --fix --unsafe-fixes` scoped to the safe rule list.
- If diffs remain, commits them back to same-repo branches or opens a labelled follow-up PR for forks.
- Always adds the `autofix:clean` label and toggles `autofix:applied`, `autofix:clean`, `autofix:debt` based on whether fixes landed and if diagnostics remain.
- Main CI continues to run non-fixing `ruff check` and fails when violations persist (no changes required in this repo because the Gate workflow already enforces it through the reusable CI jobs).

## Initial Task Checklist
- [x] Draft workflow skeleton with permissions, metadata detection, and guard logic.
- [x] Integrate Ruff installation using pinned versions from `.github/workflows/autofix-versions.env`.
- [x] Add formatting/fix steps and capture post-run diagnostics.
- [x] Implement commit/push logic for same-repo PRs and branch/PR creation for forks.
- [x] Automate label updates and optional follow-up PR comments summarising remaining diagnostics.
- [x] Document workflow behaviour in `CONTRIBUTING.md`.
