# Health Workflow Review — 2026-02-22

The goal of this pass was to catalogue every workflow under `.github/workflows` with the `health-*` prefix, verify its purpose, and decide whether it should be optimized, archived, or condensed. Notes below capture the current trigger model, what each job validates, and the immediate follow-ups (if any).

## Portfolio Observations

- **Coverage overlaps** exist between `health-70-validate-sync-manifest.yml` and `health-73-template-completeness.yml`; both gate template/manifest drift via the same Python helper. Consider merging them into a single manifest enforcement workflow to cut the duplicated runners.
- **Diagnostics vs. automation**: `health-claude-cli-auth-debug.yml` and `health-keepalive-auth-diagnostic.yml` are manual one-off troubleshooting harnesses, not automated health checks. If the debugging window has closed, move them into `archives/` (or an `ops/diagnostics` folder) to stop the health namespace from ballooning.
- **Template drift guardrails**: `health-74-template-drift.yml` only warns today. Once existing drift is eliminated, it should fail the job (or block merges via Gate) so regressions do not slip back in.
- **Consumer sync monitoring** is spread across `health-68`, `health-70`, `health-71`, and `health-72`. Centralising the registered repo parsing logic (each workflow re-parses `maint-68` today) would simplify maintenance.

## Workflow Notes

### `health-40-repo-selfcheck.yml`
- **Purpose**: Weekly repo health summary that checks required labels and enforces default-branch protection when `BRANCH_PROTECTION_TOKEN` is configured.
- **Key mechanics**: Runs every Monday at 06:20 UTC, snapshots enforcement state, and can optionally post to a PR via `workflow_dispatch`.
- **Next steps**: Confirm the admin token secret stays fresh; without it the workflow silently drops to read-only verification.

### `health-40-sweep.yml`
- **Purpose**: Gatekeeper for workflow edits; fans out to actionlint (`health-42`) and branch-protection verification (`health-44`) when `.github/workflows/**` changes.
- **Triggers**: Pull requests touching workflows, pushes to `main`, and a weekly cron at 05:05 UTC.
- **Optimizations applied**: Added a `run_branch_protection` manual-dispatch input plus downstream gating so maintainers can skip the API-heavy branch guard leg when they only need to re-run actionlint. The detect job now parses the dispatch inputs once and reuses the flag across jobs, avoiding unnecessary workflow invocations and API calls on ad-hoc lint runs.

### `health-41-repo-health.yml`
- **Purpose**: Monday sweep for stale branches/PRs with rate-limit awareness.
- **Highlights**: Skips automatically if API quota drops below 2,000 to avoid starving keepalive; writes summaries to `GITHUB_STEP_SUMMARY`.
- **Optimizations applied**: Manual dispatchers can now pass `include_branches=false` and/or `include_prs=false` to bypass the multi-page listings and commit lookups when they only need part of the report, significantly reducing API calls during targeted reruns while keeping the scheduled sweep unchanged.
- **Bug fix**: Inputs are now read via `GITHUB_EVENT_PATH` and exported into `GITHUB_ENV`, fixing the `PROMPT_FILE`-style empty-variable bug that caused the workflow to fail when the dispatch inputs were omitted.

### `health-42-actionlint.yml`
- **Purpose**: Central actionlint runner (v1.7.3) with reviewdog integration.
- **Observations**: Supports workflow_call + manual dispatch + PR review. Cache plumbing + allowlist already in place.
- **Optimizations applied**: Dropped the unused GitHub App token mint step so ad-hoc lint runs no longer spend an API call before doing any work; caches + install fallbacks already cover the actual compute cost.

### `health-43-ci-signature-guard.yml`
- **Purpose**: Ensures `pr-00-gate` stays wired to `signature-verify` fixtures whenever guard logic changes.
- **Optimizations applied**: Removed the unused GitHub App token mint step; the workflow only needs repository read access to fetch fixture files, so skipping the token mint avoids a gratuitous API call on every run.

### `health-44-gate-branch-protection.yml`
- **Purpose**: Enforces and verifies required contexts for the default branch using `tools/enforce_gate_branch_protection.py`.
- **Observations**: Supports both workflow_call (for reuse) and PR events. Admin token optional but required for enforcement.
- **Optimizations applied**: Removed the unused GitHub App token mint step; the workflow already relies on `BRANCH_PROTECTION_TOKEN` (when present) plus `GITHUB_TOKEN` for read-only verification, so skipping the extra mint saves an API roundtrip on every run.

### `health-50-security-scan.yml`
- **Purpose**: CodeQL Python scan on push/PR plus weekly schedule.
- **Optimizations applied**: Removed the unnecessary GitHub App token mint; CodeQL already runs with the prioritized PAT (`CODEQL_TOKEN`) or falls back to the installation token, so skipping the extra mint saves an API roundtrip per run.

### `health-67-integration-sync-check.yml`
- **Purpose**: Validates `Workflows-Integration-Tests` stays aligned with template workflows + `autofix-versions.env`.
- **Observations**: Automatically files `integration-sync` drift issues with clear action lists.
- **Optimizations applied**: Added workflow_dispatch inputs (`run_ci_check`, `run_version_check`, `run_input_check`) so targeted reruns can skip the expensive clone/compare loops they don't need while still reporting drift for the enabled sections.

### `health-68-consumer-sync-drift.yml`
- **Purpose**: Compares registered consumer repos against the template files and opens/updates `consumer-sync` drift issues.
- **Optimizations applied**: Added `scripts/list_registered_consumer_repos.py` and updated the workflow to call it, so the manifest parsing logic is reusable (and shared with future workflows) instead of embedding bespoke inline Python.

### `health-70-validate-sync-manifest.yml`
- **Purpose**: Enforces that templates, prompts, scripts, and workflows are represented in `.github/sync-manifest.yml`.
- **Optimizations applied**: Replaced the inline Python with a call to `scripts/validate_template_completeness.py --strict --source sync-manifest` so Health 70 now shares its validator with Health 73 and auto-writes clearer run summaries.

### `health-71-sync-health-check.yml`
- **Purpose**: Daily monitor for the `maint-68-sync-consumer-repos` workflow; creates/updates GitHub issues when the sync fails repeatedly or goes stale.
- **Optimizations applied**: Replaced the inline repo parsing with the shared `scripts/list_registered_consumer_repos.py` helper (matching health-68) and dropped the unused GitHub App token mint so the workflow only uses the default installation token for its API calls.

### `health-72-template-sync.yml`
- **Status**: Pending detailed review — leaving documentation unchanged until we confirm what (if anything) needs to be optimized in this workflow.

### `health-73-template-completeness.yml`
- **Purpose**: Runs `scripts/validate_template_completeness.py --strict` on pushes/PRs.
- **Optimizations applied**: Shares the same script as Health 70 (no inline duplication) and now skips minting a GitHub App token, since the validator runs locally without extra API calls.

### `health-74-template-drift.yml`
- **Purpose**: Compares production `agents-*` workflows with their template counterparts and warns if they diverge by >50 lines.
- **Next steps**: After the outstanding drift is cleared, flip the workflow to fail instead of warn so regressions are blocked earlier.
- **Optimizations applied**: Expanded the drift mapping to include every current agents workflow so the comparison stays comprehensive as new agent jobs land.

### `health-75-api-rate-diagnostic.yml`
- **Purpose**: Hourly snapshots of PAT/App rate-limit pools plus optional consumer-repo churn + load-balancer drill-downs.
- **Optimizations applied (2026-02-22)**:
  - Dialed the cron back to hourly and made consumer repo scans/manual-only (`include_consumer_repos=true` on dispatch) so the workflow stops hammering every registered repo by default.
  - Added two new dispatch inputs (`run_load_sharing_checks`, `verify_actions_access`) so the expensive token-rotation simulation and per-token workflow-run probes only fire when explicitly requested.
  - Patched the `alert-on-high-usage` job to inspect the real summary keys (`owner_pr_pat`, `workflows_app`, etc.) so high-utilization alerts finally trigger when those pools exceed 85%.
- **Next steps**: Keep building historical storage for the summary JSON and consider pushing consumer-repo metrics into a reusable helper so health-67/68 can share it.

### `health-claude-cli-auth-debug.yml`
- **Purpose**: Manual debugging harness for the Claude Code CLI auth path (explicitly labelled “delete after debugging”).
- **Status (2026-02-22)**: Retired from Actions and moved to the archive to separate a temporary harness from the automated roster. [Historical YAML](https://github.com/stranske/Workflows/blob/67c2558643792c08e2063bbd0c4133c561fb009e/archives/diagnostics/health-claude-cli-auth-debug.yml) · [Current troubleshooting](../ci/WORKFLOW_SYSTEM.md#keepalive-and-cli-troubleshooting)

### `health-codex-auth-check.yml`
- **Purpose**: Twice-daily guard that inspects `CODEX_AUTH_JSON` JWT expiry, filing `auth-expiring` issues before tokens lapse.
- **Optimizations applied (2026-02-22)**: Dropped the unnecessary GitHub App token mint + checkout override so each run now uses the default installation token for its two API calls (list issue + create issue), shaving an API request per run without changing behavior.

### `health-keepalive-auth-diagnostic.yml`
- **Purpose**: Manual runner that validates GitHub App PATs (WORKFLOWS_APP/KEEPALIVE_APP) and Claude auth secrets end-to-end.
- **Status (2026-02-22)**: Retired from Actions and moved to the archive. [Historical YAML](https://github.com/stranske/Workflows/blob/67c2558643792c08e2063bbd0c4133c561fb009e/archives/diagnostics/health-keepalive-auth-diagnostic.yml) · [Current troubleshooting](../ci/WORKFLOW_SYSTEM.md#keepalive-and-cli-troubleshooting)

### `health-keepalive-e2e.yml`
- **Purpose**: Validates keepalive orchestration logic and (optionally) executes a real Codex CLI ping when labeled with `e2e:codex-ping`.
- **Optimizations applied (2026-02-22)**: Removed the redundant GitHub App token mints in both the detect + orchestration jobs so the fast path only uses the installation token it already has, shaving two auth calls off every run without changing coverage.
