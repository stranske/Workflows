# CI Workflow Consolidation Plan — Post Issue #2190 Snapshot

Last updated: 2026-10-12

Issue #2190 completed the consolidation roadmap that began in #1166/#1259. The repository now exposes only the reusable
workflows required by the trimmed automation surface.

## Current State
- Four reusable workflows remain (`reusable-10-ci-python.yml`, `reusable-12-ci-docker.yml`, `reusable-18-autofix.yml`,
  `reusable-16-agents.yml`). The reusable CI matrix is now hosted directly inside `selftest-reusable-ci.yml`, eliminating
  the extra wrapper layer while preserving manual dispatch controls.
- Visible workflows in the Actions tab were reduced to the final set documented in `docs/ci/WORKFLOW_SYSTEM.md` and `docs/ci/WORKFLOWS.md`.
- All auxiliary wrappers (gate orchestrators, labelers, watchdog forwards, etc.) were deleted, with the shared intake (`agents-63-issue-intake.yml`) now servicing both label-driven Codex automation and ChatGPT sync.

## Completed Consolidation Actions
| Area | Action |
|------|--------|
| Agent automation | Removed `agents-41*`, `agents-42-watchdog.yml`, `agents-44-copilot-readiness.yml`, and `agents-45-verify-codex-bootstrap-matrix.yml`; consolidated around `agents-70-orchestrator.yml` + `reusable-16-agents.yml`, then routed label-driven Codex bootstraps through `agents-63-issue-intake.yml`.
| Maintenance | Deleted legacy hygiene/self-test workflows (`maint-31`, `maint-34`, `maint-37`, `maint-38`, `maint-43`, `maint-44`, `maint-45`, `maint-48`, `maint-49`, `maint-52`, `maint-60`) and, after consolidation, replaced the manual `selftest-8X-*` wrappers with the single `selftest-reusable-ci.yml` entry point that now embeds the verification matrix. ChatGPT intake now runs directly through `agents-63-issue-intake.yml`, keeping the manual dispatch surface consolidated. |
| PR checks | Removed auxiliary PR workflows (gate orchestrator, labeler, workflow lint, CodeQL, dependency review, path labeler) to align with the two final checks.

## Follow-Up Guardrails
- `tests/test_workflow_naming.py` enforces the `<area>-<NN>-<slug>.yml` convention and inventory coverage.
- `tests/test_workflow_agents_consolidation.py` verifies the orchestrator inputs and ensures legacy agent workflows do not return.
- `docs/ci/WORKFLOWS.md` is the authoritative description of the remaining automation footprint.

## Future Considerations
1. The legacy `maint-90-selftest.yml` schedule is retired; dispatch `selftest-reusable-ci.yml`
   when reusable CI verification is needed.
2. Revisit CodeQL or dependency review if security tooling is reintroduced in a dedicated follow-up issue.
3. Validate external consumers when adjusting inputs on `reusable-10-ci-python.yml` or `reusable-12-ci-docker.yml`.

No additional consolidation actions are planned at this time.
