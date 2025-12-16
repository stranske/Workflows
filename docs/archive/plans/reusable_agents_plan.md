# Reusable Agents Workflow Update Plan

## Scope and Key Constraints
- Normalize all consumers to invoke a single reusable workflow entrypoint (`.github/workflows/reusable-16-agents.yml`).
- Ensure the reusable workflow declares `on: workflow_call` with typed, validated inputs required by consumers.
- Centralize timeout configuration inside the reusable workflow so callers do not define per-job timeouts.
- Preserve existing caller functionality and secrets contract while updating workflow names/paths.
- Avoid introducing breaking changes to unrelated workflows or jobs.

## Acceptance Criteria / Definition of Done
1. `.github/workflows/reusable-16-agents.yml` exposes a `workflow_call` trigger with documented inputs and defaults that cover all current consumer needs.
2. Every job inside the reusable workflow (`bootstrap`, `readiness`, `watchdog`, and any other long-running job) defines an explicit `timeout-minutes` value aligned with operational expectations.
3. All wrapper workflows reference only `.github/workflows/reusable-16-agents.yml`; obsolete or duplicate reusable workflow files are removed or deprecated.
4. CI validation passes for the updated workflows, confirming syntax correctness and successful invocation paths.
5. Documentation (workflow README or inline comments) reflects the single-entrypoint design and timeout responsibilities.

## Initial Task Checklist
- [x] Audit current reusable workflow files and identify callers, documenting required inputs/secrets.
- [x] Update `.github/workflows/reusable-16-agents.yml` to use `on: workflow_call` and declare validated inputs with defaults.
- [x] Add `timeout-minutes` to each long-running job within the reusable workflow.
- [x] Adjust all calling workflows to reference the updated reusable entrypoint and remove references to deprecated files.
- [x] Run workflow linter/CI checks (e.g., `act`, `yaml-lint`, or GitHub Actions dry-run) to ensure configuration correctness.
- [x] Update documentation to explain the centralized entrypoint and timeout management strategy.
