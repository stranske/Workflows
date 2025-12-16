# Agents Guard – Planning Notes

## Scope and Key Constraints
- Implement a `.github/workflows/agents-guard.yml` workflow that runs on `pull_request` events scoped via `paths` plus label-driven `pull_request_target` events for `agent:*` labels.
- Workflow must execute from the default branch context and use only `contents: read` and `pull-requests: write` permissions; no additional scopes or secrets.
- Guarded files: both "Agents 63" workflow files and the "Orchestrator" workflow/file (exact filenames to be confirmed from repository history). Deletions, renames, or missing files must cause a failure.
- Modifications to guarded files are allowed only when the PR has the `agents:allow-change` label **and** at least one CODEOWNER approval.
- The workflow should post a single, human-friendly failure comment explaining how to proceed, avoiding duplicate comments across runs by using a per-PR concurrency group.
- The failure should block merging by marking the status check as failed, and the check must be added to the repository’s required status checks list.
- Solution must rely on GitHub API interactions available in GitHub Actions and should remain compatible with forks (no write access to repo contents beyond comments).

## Acceptance Criteria / Definition of Done
- [x] Workflow triggers only for PRs that touch `.github/workflows/agents-*.yml` files or carry an `agent:*` label.
- [x] Workflow fails immediately with an explanatory comment if any guarded file is deleted or renamed in a PR.
- [x] Workflow fails with an explanatory comment when guarded files are modified without the `agents:allow-change` label.
- [x] Workflow fails with an explanatory comment when guarded files are modified without at least one CODEOWNER approval, even if the label is present.
- [x] Workflow passes when guarded files are modified, the `agents:allow-change` label is present, and at least one CODEOWNER approval exists.
- [x] Failure comment appears only once per PR and includes guidance on resolving each guard condition.
- [x] Repository owners can add the workflow’s status check to required checks without additional configuration and see only a single guard status.

## Initial Task Checklist
- [x] Inventory the exact filenames for the "Agents 63" workflows and the orchestrator to ensure the guard targets the correct paths.
- [x] Design the GitHub Actions workflow structure (trigger, permissions, job layout) and choose the tooling (e.g., `actions/github-script` vs. custom action).
- [x] Implement logic to fetch changed files via the GitHub API and detect deletions/renames affecting guarded files.
- [x] Implement guard logic that evaluates label presence and CODEOWNER approvals.
- [x] Add idempotent PR commenting to explain failures without duplication.
- [x] Test the workflow behavior using workflow dry-runs or mock PR scenarios (e.g., `act` or manual triggering) to validate each acceptance criterion.
- [x] Coordinate with repository settings to add the new status check to required checks after verification. (Completed by adding **Agents Guard / Enforce agents workflow protections** to the branch-protection enforcement script and documentation.)

## Completion Notes
- Unified `agents-guard.yml` workflow now scopes runs via `paths` and `pull_request_target` label hooks while using per-PR concurrency to keep a single status context.
- Guard evaluation lives in `.github/scripts/agents-guard.js`, ensuring label and CODEOWNER requirements are enforced alongside deletion/rename detection and deduplicated PR comments.
- Branch protection automation (`tools/enforce_gate_branch_protection.py`) and contributor documentation (`docs/ci/AGENTS_POLICY.md`, `docs/ci/WORKFLOW_SYSTEM.md`) reference the new required status so the guard remains enforced on the default branch.
- Validation suite covers the guard logic (`tests/test_agents_guard.py`), branch-protection tooling (`tests/tools/test_enforce_gate_branch_protection.py`), and workflow naming/metadata (`tests/test_workflow_naming.py`).

## Validation Notes
- Deleting or renaming any of the guarded workflows produces an immediate failure with actionable guidance.
- Modifying a guarded workflow without the `agents:allow-change` label fails and explains how to request the label.
- Modifying a guarded workflow with the label but without a CODEOWNER approval fails and reminds reviewers to approve.
- A guarded workflow passes once both the label and at least one CODEOWNER approval are present.
