# Consolidated Self-Test Runner Plan

> **Status (2026-11-15, Issue #2728):** Completed. `selftest-reusable-ci.yml` is now the
> sole self-test workflow and runs on the nightly 06:30 UTC cron as well as
> `workflow_dispatch`. The legacy wrappers (`maint-43-selftest-pr-comment.yml`,
> `maint-44-selftest-reusable-ci.yml`, `maint-48-selftest-reusable-ci.yml`,
> `selftest-pr-comment.yml`, `selftest-reusable-ci.yml`) exist only in git history
> with their rationale captured in [`ARCHIVE_WORKFLOWS.md`](../archive/ARCHIVE_WORKFLOWS.md).
> Guardrails in `tests/test_workflow_selftest_consolidation.py` enforce this
> single-entry inventory.
>
> **Update (Issue #2814):** The active workflow now lives at
> `selftest-reusable-ci.yml`, which reuses the same triggers and inputs,
> delegates each scenario to `reusable-10-ci-python.yml`, and publishes a compact
> matrix summary described in [`docs/ci/SELFTESTS.md`](SELFTESTS.md).

## Scope and Key Constraints
- Replace the existing collection of self-test GitHub Actions workflows with a single parameterized runner that can reproduce all current automation entry points (PR comment trigger, reusable CI job, main pipeline, etc.).
- Preserve behaviour for each retired workflow, including custom comment formatting, PR metadata handling, and conditional execution logic, while reducing maintenance duplication.
- Stay within GitHub Actions limits for reusable workflows (20 inputs, matrix size, job duration) and maintain compatibility with the repositories that currently consume the reusable workflows.
- Maintain "docs-only" detection and fast-pass behaviour so documentation updates continue to skip unnecessary self-test executions.
- Coordinate rollout so the consolidated runner is available in parallel until parity is demonstrated, then remove the legacy workflow files in a single follow-up PR.

## Acceptance Criteria / Definition of Done
1. A single workflow file (e.g., `.github/workflows/selftest-reusable-ci.yml`) defines a matrix that covers all former self-test entry points, including:
   - PR comment-triggered self-tests with optional PR number override.
   - Reusable CI workflow for other repos/jobs that currently import `selftest-reusable-ci.yml` variants.
   - Manual dispatch with inputs for custom titles, rationale, and target ref.
2. The legacy workflow files `maint-43-selftest-pr-comment.yml`, `maint-44-selftest-reusable-ci.yml`, `maint-48-selftest-reusable-ci.yml`, `selftest-pr-comment.yml`, and `selftest-reusable-ci.yml` are deleted after confirming feature parity.
3. Documentation references (`WORKFLOW_SYSTEM.md`, `WORKFLOWS.md`, and any workflow catalog entries) are updated to describe the consolidated runner and its inputs.
4. CI passes with the new workflow configuration, and no duplicate self-test workflows appear in the Actions tab for new commits.
5. Automated tests (unit or integration) covering workflow configuration helpers are updated/added where applicable, and they pass locally/CI.

## Initial Task Checklist
- [x] Audit the existing self-test workflows to catalogue triggers, inputs, outputs, and dependent jobs.
- [x] Design the consolidated workflow matrix, mapping each legacy use case to a matrix entry or conditional branch.
- [x] Draft the new `.github/workflows/selftest-reusable-ci.yml` with reusable inputs and shared job logic.
- [x] Implement any supporting composite actions or scripts needed to share logic between matrix entries.
- [x] Update documentation (`docs/ci/WORKFLOW_SYSTEM.md`, `docs/ci/WORKFLOWS.md`, etc.) to reflect the new runner and migration guidance.
- [x] Run targeted tests (e.g., `pytest tests/test_workflow_selftest_consolidation.py`) to validate helper logic.
- [x] Remove legacy workflow files once parity is verified and ensure CI remains green.
- [x] Communicate rollout plan (e.g., changelog note or internal announcement) if required by project governance.
