# Archived GitHub Workflows (updated 2027-02-15)

This document records the archival and eventual deletion of legacy agent-related workflows now replaced by consolidated reusable pipelines. The most recent sweep (Issue #1419) retired the reusable agent matrix in favour of the focused assigner/watchdog pair. The follow-up sweep for Issue #1669 removed the on-disk archive directory so the history now lives exclusively in git along with this ledger.

## Archived

### Maintenance sweep (Issue #2823)
- `ci.yml` → [`pr-00-gate.yml`](../../.github/workflows/pr-00-gate.yml) — Gate now fans out to the reusable Python matrix so the standalone CI wrapper is redundant.
- `docker.yml` → [`pr-00-gate.yml`](../../.github/workflows/pr-00-gate.yml) — The Gate workflow’s Docker smoke job replaces the legacy bespoke Docker entry point.
- `gate.yml` → [`pr-00-gate.yml`](../../.github/workflows/pr-00-gate.yml) — Consolidated Gate orchestrator supersedes the historical aggregator wrapper.
- `docs-only.yml` → [`pr-00-gate.yml`](../../.github/workflows/pr-00-gate.yml) — Gate’s docs-only detection and summary comment absorb the bespoke notice workflow.
- `pr-14-docs-only.yml` → [`pr-00-gate.yml`](../../.github/workflows/pr-00-gate.yml) — The numbered docs-only fast path stays removed; Gate enforces the same checks.
- `pr-status-summary.yml` → Gate summary job (`.github/workflows/pr-00-gate.yml`, job `summary`) — The inline summary now owns the single PR comment, eliminating duplicate reporting.
- `ci-matrix-summary.yml` → Gate summary job (`.github/workflows/pr-00-gate.yml`, job `summary`) — Coverage and failure rollups ride the Gate summary instead of the retired matrix helper.
- `check-failure-tracker.yml` → Gate summary job (`.github/workflows/pr-00-gate.yml`, job `summary`) — The post-CI summary now maintains the failure-tracker issue directly.
- `repo-health-self-check.yml` → [`health-40-repo-selfcheck.yml`](../../.github/workflows/health-40-repo-selfcheck.yml) — The WFv1 “health 40” refactor replaced the ad-hoc repo self-check job.
- `repo-health-nightly.yml` → [`health-41-repo-health.yml`](../../.github/workflows/health-41-repo-health.yml) — Weekly repo-health audits now run under the numbered Health 41 workflow.
- `ci-signature-guard.yml` → [`health-43-ci-signature-guard.yml`](../../.github/workflows/health-43-ci-signature-guard.yml) — Signature verification moved to the numbered health guard.
- `agents-47-verify-codex-bootstrap-matrix.yml` → [`agents-70-orchestrator.yml`](../../.github/workflows/agents-70-orchestrator.yml) — Orchestrator dispatch verifies bootstrap compatibility via the reusable agents toolkit.
- `assign-to-agents.yml` → [`agents-63-issue-intake.yml`](../../.github/workflows/agents-63-issue-intake.yml) + [`agents-70-orchestrator.yml`](../../.github/workflows/agents-70-orchestrator.yml) — Label-driven intake and orchestrator now assign Codex issues without the standalone helper.

### Legacy agent watchdog
- **Removed file**: `agent-watchdog.yml` (retired with the Issue #1419 consolidation sweep).
- **Replacement**: watchdog coverage now ships as the `enable_watchdog` switch inside `Agents 70 Orchestrator`, so both the 20-minute schedule and ad-hoc manual runs execute the same reusable watchdog path.
- **Verification (2026-10-18, Issue #2562)**: Confirmed the standalone workflow remains absent, the orchestrator forwards `enable_watchdog` exclusively to the reusable job, and the reusable `watchdog` job stays gated behind `inputs.enable_watchdog == 'true'` with its repository sanity check intact. No dedicated secrets or environment variables remained unique to the retired workflow.

### Retired self-tests
- **Archived files**: Historical copies of `maint-90-selftest.yml` and `reusable-99-selftest.yml` now live exclusively in git history. Their on-disk archive home (`Old/workflows/`) was removed during Issue #2728 once the consolidated runner proved stable.
- **Replacement**: Manual verification now runs through `selftest-reusable-ci.yml`, which delegates every scenario to `reusable-10-ci-python.yml` via `jobs.<id>.uses`. Earlier wrappers (`selftest-80-pr-comment.yml`, `selftest-82-pr-comment.yml`, `selftest-83-pr-comment.yml`, `selftest-84-reusable-ci.yml`, `selftest-88-reusable-ci.yml`, `selftest-81-reusable-ci.yml`) persist only in history for reference.
- **Comment wrappers retired (Issue #2720)**: The redundant PR comment helpers `maint-43-selftest-pr-comment.yml`, `pr-20-selftest-pr-comment.yml`, and `selftest-pr-comment.yml` were deleted once the consolidated runner and Gate summary comment proved stable. Historical references now live exclusively in this ledger; rely on the `Selftest: Reusables` workflow comment mode or the Gate summary for PR annotations.
- **Historical note (2026-11-15, Issue #2728)**: `selftest-reusable-ci.yml` was previously removed in favour of scheduling `selftest-runner.yml` directly. The nightly cron continued to run through the runner’s summary mode until the Issue #2814 consolidation restored the reusable entry point.
- **2025-10-19 disablement (Issue #2728)**: Legacy workflow entries (`selftest-pr-comment.yml`, `maint-43-selftest-pr-comment.yml`, `maint-44-selftest-reusable-ci.yml`, `maint-48-selftest-reusable-ci.yml`, `pr-20-selftest-pr-comment.yml`) were manually disabled via `gh workflow disable` so that, among self-test workflows, only the **Selftest Runner** remains visible in the Actions UI.
- **Issue #2814 consolidation (2026-12-09)**: `selftest-runner.yml` was superseded by `selftest-reusable-ci.yml`, restoring the canonical workflow name “Selftest: Reusables,” keeping the nightly cron at `30 6 * * *`, and trimming the run summary down to a compact matrix table in `GITHUB_STEP_SUMMARY`. Documentation now points to [`docs/ci/SELFTESTS.md`](../ci/SELFTESTS.md) and [`docs/ci/issue-2814-plan.md`](../ci/issue-2814-plan.md) for scenario details and completion evidence.

## Removed Legacy Files (Cleanup PR for Issue #1259)
All deprecated agent automation workflows were deleted from `.github/workflows/` on 2025-09-21 once the stabilization window for the reusable equivalents closed. Historical copies formerly lived under `.github/workflows/archive/` but that directory was removed on 2026-10-07 as part of the Issue #1669 cleanup. Retrieve any prior YAML from git history when needed.

| Legacy Workflow | Historical Archive Path | Replacement Path | Replacement Mode |
|-----------------|-------------------------|------------------|------------------|
| `agent-readiness.yml` | `archive/agent-readiness.yml` (deleted 2026-10-07) | `reuse-agents.yml` → `agents-70-orchestrator.yml` | `enable_readiness=true` |
| `agent-watchdog.yml` | `archive/agent-watchdog.yml` (deleted 2026-10-07) | `reuse-agents.yml` → `agents-70-orchestrator.yml` | `enable_watchdog=true` |
| `codex-preflight.yml` | `archive/codex-preflight.yml` (deleted 2026-10-07) | `reuse-agents.yml` (legacy) | `enable_preflight=true` |
| `codex-bootstrap-diagnostic.yml` | `archive/codex-bootstrap-diagnostic.yml` (deleted 2026-10-07) | `reuse-agents.yml` (legacy) | `enable_diagnostic=true` |
| `verify-agent-task.yml` | `archive/verify-agent-task.yml` (deleted 2026-10-07) | `reuse-agents.yml` (legacy) | `enable_verify_issue=true` |

## Additional Archived Workflows
- (2026-02-07) `codex-issue-bridge.yml`, `reuse-agents.yml`, and the legacy `agents-consumer.yml` moved to the archive before the assigner/watchdog consolidation. The WFv1 renumbering landed in 2026-09 (`agents-40-consumer.yml`, `agents-41-assign-and-watch.yml`, wrappers, plus `reusable-90-agents.yml`) and was superseded by Issue #2190 (`agents-70-orchestrator.yml`, `reusable-16-agents.yml`). Issue #2493 temporarily reintroduced the consumer shim (as `agents-61-consumer-compat.yml`) for manual dispatch, but it has now been retired alongside `agents-62-consumer.yml` in favour of the orchestrator-only surface.
- (2026-10-12) Issue #2466 removed the last on-disk copy of the historical slug; Issue #2493 restored the workflow with the corrected `jobs.<id>.uses` contract and a concurrency guard to prevent repeated manual triggers from piling up.
- (2026-10-20) Issue #2650 confirmed `.github/workflows/agents-62-consumer.yml` remains deleted and refreshed docs/tests so the Codex issue bridge feeds only the orchestrator entry point.
- (2026-11-07) Issue #2656 final check confirmed README, CONTRIBUTING, and docs/ci/WORKFLOWS.md route through the Workflow System Overview and that references to retired consumer shims now live solely in this ledger.
- (2026-11-08) Issue #2656 documentation alignment refresh ensured README.md, CONTRIBUTING.md, `docs/ci/WORKFLOWS.md`, `docs/WORKFLOW_GUIDE.md`, and `docs/ops/codex-bootstrap-facts.md` point historical lookups back to this archive.
- (2026-11-09) Issue #2656 verification confirmed Agents.md now defers to the archive and reiterates that the orchestrator is the sole automation entry point.
- (2026-11-10) Issue #2656 documentation sweep scrubbed remaining references to retired consumer wrappers so they are mentioned exclusively in this ledger.
- (2026-11-11) Issue #2656 follow-up removed the stale `reusable-90-ci-python.yml` reference from `docs/ci-workflow.md` and reiterated that matrix verification now runs through `reusable-10-ci-python.yml` or the consolidated `selftest-reusable-ci.yml` workflow.
- (2026-11-12) Issue #2656 completion audit verified README.md, CONTRIBUTING.md, `docs/ci/WORKFLOWS.md`, and `docs/ci/WORKFLOW_SYSTEM.md` all route readers through the overview first, now link directly to the keep vs retire roster anchor, and confirm that references to retired workflows remain confined to this archive.
- (2026-09-30) Standalone `gate.yml` wrapper deleted (Issue #1657). The subsequent consolidation (Issue #2195) folded the aggregator logic into the single `ci / python` job inside `pr-10-ci-python.yml`; no archived copy retained because the YAML was invalid.
- (2026-10-05) `autoapprove.yml` and `enable-automerge.yml` permanently retired once `maint-45-merge-manager.yml` proved stable (guard test asserts documentation coverage).
- (2026-10-05) `guard-no-reuse-pr-branches.yml` and `lint-verification.yml` removed after governance documentation and branch protection policies caught up with the consolidated CI stack.
- (2026-10-05) Remaining stub archives under `Old/.github/workflows/` were deleted; historical copies are available via git history and the references below.
- (2026-10-07) `.github/workflows/archive/` removed entirely; Issue #1669 ledger (this file) is now the canonical index for prior workflow names.
- (2026-10-08) Issue #1669 verification sweep confirmed both archive directories remain absent and no additional workflows required archival.
- (2026-10-09) Follow-up audit reran the guard suite and filesystem checks; `.github/workflows/archive/` and `Old/.github/workflows/` remain deleted with inventory logged in [`docs/ci/WORKFLOW_SYSTEM.md`](../ci/WORKFLOW_SYSTEM.md).
- (2026-10-10) Latest verification re-ran the workflow guard tests and filesystem sweep—no archived directories reappeared.
- (2026-10-14) Issue #2463 confirmed the standalone `agent-watchdog.yml` workflow remains removed and documentation now directs contributors to the orchestrator `enable_watchdog` toggle.
- (2026-11-18) Guard consolidation removed `health-45-agents-guard.yml` and `agents-critical-guard.yml`, replacing both with the unified [`agents-guard.yml`](../../.github/workflows/agents-guard.yml) workflow so protected surfaces stay enforced without duplicate guard contexts.
- (2026-10-13) Issue #2494 revalidated that `agent-watchdog.yml` stays deleted, recorded the orchestrator manual-dispatch watchdog run, and refreshed contributor docs to reference the orchestrator-only path.
- (2026-10-12) Issue #2378 relocated the remaining self-test wrappers to `Old/workflows/` (`maint-90-selftest.yml`, `reusable-99-selftest.yml`) and updated docs to reference their archival home.

## Archived in Issue #2378

- `maint-90-selftest.yml` – moved to `Old/workflows/maint-90-selftest.yml`.
- `reusable-99-selftest.yml` – moved to `Old/workflows/reusable-99-selftest.yml`; reinstated in `.github/workflows/` by Issue #2379 after being rewritten to use `jobs.<id>.uses`.

_(Historical note: the `Old/workflows/` directory was removed in Issue #2728; retrieve these YAML files from git history when needed.)_
- `selftest-83-pr-comment.yml` – originally removed; reintroduced in Issue #2525 as a manual-only maintenance comment helper.
- `selftest-84-reusable-ci.yml` – initially removed when coverage shifted to the reusable matrix; restored in Issue #2525 as a
  manual summary wrapper delegating to `selftest-81-reusable-ci.yml` (historical name for the matrix now embedded in `selftest-reusable-ci.yml`).
- `selftest-88-reusable-ci.yml` – short-lived experimental matrix retired in 2025, reinstated by Issue #2525 to exercise dual
  runtime scenarios on demand.
- `selftest-82-pr-comment.yml` – previously deleted PR comment bot; revived in Issue #2525 with workflow_dispatch-only semantics.

_(2026-11-04 update) The Issue #2651 consolidation removed the reinstated wrappers above and replaced them with the single `selftest-reusable-ci.yml` entry point. The notes remain for historical tracking only._

## Retired Autofix Wrapper
- Legacy `pr-02-autofix.yml` (pre-2025) was deleted during the earlier cleanup. As of 2026-02-15 the consolidated Gate summary job (previously `maint-32-autofix.yml`) began handling small fixes and trivial failure remediation. In 2026-10 the streamlined PR-facing `pr-02-autofix.yml` workflow was reinstated (Issue #2380) and delegated to the same reusable composite used by the summary job; it has since been removed again so the Gate summary job remains the only autofix entry point.

## Rationale
The 2025 cleanup centralized agent probe, diagnostic, and verification logic into `reuse-agents.yml`. In 2026 this was further simplified: `agents-41-assign-and-watch.yml` and its wrappers gave way to the single `agents-70-orchestrator.yml` entry point that calls `reusable-16-agents.yml`.

## Rollback Procedure
If a regression is traced to consolidation:
1. Re-enable the specific archived YAML by copying its historical content from git history (pre-archival commit) back into `.github/workflows/`.
2. File an issue documenting the gap vs the reusable job’s behavior.
3. Re-run a targeted `workflow_dispatch` on the restored file for confirmation.

## Follow-Up Tasks
| Task | Owner | Priority |
|------|-------|----------|
| Monitor assigner/watchdog telemetry and add readiness probing only if gap resurfaces | TBD | P3 |

## Verification Checklist
- [x] Archive index maintained: `docs/archive/ARCHIVE_WORKFLOWS.md`
- [x] Stub headers inserted in original workflows marking ARCHIVED status
- [x] Replacements confirmed operational (`agents-70-orchestrator.yml` present; legacy wrappers retired)
- [x] 2026-10-08 audit logged (see "Verification log" in [`docs/ci/WORKFLOW_SYSTEM.md`](../ci/WORKFLOW_SYSTEM.md))

---
Generated as part of workflow hygiene initiative.
