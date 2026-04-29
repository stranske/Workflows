# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Breaking changes are called out with a **BREAKING** marker and scheduled according to the policy in `COMPATIBILITY.md`.

## [Unreleased]

### Added
- Repo-review subsystem: weekly preflight workflow plus the `scripts/repo_review_evaluator.py`, `scripts/repo_review_issue_quality.py`, and `scripts/upload_repo_review_issues.py` pipeline. Reviews must now carry semantic content, evidence traces, process-chain checkpoints, a duplicate-detection guard, and a freshness check before any issues are filed; the contract is documented in `docs/ops/REPO_REVIEW_PROCESS.md`.
- Sync/Dependabot campaign queue (`maint-82-sync-dependabot-campaign.yml` + `.github/scripts/sync_dependabot_campaign.js`): the campaign issue is now the durable queue, with claim-leases, source-review history, source-freshness tracking, and parse contracts so concurrent sweeps don't race or auto-close active campaigns.
- Bot-comment authentication coverage: `.github/scripts/bot_comment_auth_coverage.js` plus reusable auth-policy knob in `reusable-bot-comment-handler.yml` track which app/auth path each bot comment used, with hard-block enforcement gated behind eligibility evidence.
- Verifier and Codex CLI freshness monitoring: `health-76-codex-cli-freshness.yml` plus `scripts/check_codex_cli_freshness.py`, with verifier ledger, setup preflight, follow-up policy metrics, and legacy-model warning suppression in `reusable-agents-verifier.yml`.
- Workflow action-pin contract enforced by `scripts/check_workflow_action_pins.py` (PR #1925), so reusable and first-party workflows pin third-party actions to commit SHAs consistently.
- GitNexus optional cross-repo indexing fleet (`docs/ops/GITNEXUS.md`, `docs/ops/bin/gitnexus_fleet.sh`) for opportunistic blast-radius checks against the canonical repo set.
- Release workflow now refreshes the floating `v1` tag on every `v1.x` release, and the floating-tag maintenance job also runs when a `v1.x` release is published.
- Tests cover creating the floating `v1` tag when it does not yet exist, ensuring it points to the latest `v1.x` release.
- Documentation now outlines the recommended versioning strategy, including when to use pinned (`@v1.0.0`) versus floating (`@v1`) tags in both the README and Integration Guide.
- Compatibility policy captured in `COMPATIBILITY.md`, including deprecation timelines and the two-major support window.
- Gate now emits an `autofix_gate_failure` repository dispatch when it fails, providing a hook that consumer workflows (or the new dispatch handler) can use to trigger the Agents Autofix Loop with the same payload so Codex/Claude reroutes execute even for PR-only Gate runs.

### Changed
- Weekly metrics pipeline rewritten end-to-end: `agents-weekly-metrics.yml` plus new `weekly_metrics_artifacts.js` and `weekly_metrics_download_manifest.js`, and `aggregate_agent_metrics.py` extended with parse attribution, NDJSON keepalive repair, artifact-id preservation, bounded artifact selection, and a download manifest.
- Consumer-sync hardening across `maint-68-sync-consumer-repos.yml`, `maint-71-merge-sync-prs.yml`, and `health-67-integration-sync-check.yml`: header-aware diff, run-report contracts, drift-issue-body assembly, and token diagnostics in `check_consumer_sync_drift.py`.
- Workflow Python pinned to 3.12 across the fleet; legacy `CODESPACES_WORKFLOWS` token paths retired in favor of canonical app-auth and the bot-comment wrapper now prefers the GitHub App client ID.
- `docs/INTEGRATION_GUIDE.md` quick-setup now points new consumers at the current default surface (`agents-80-pr-event-hub.yml`, `agents-81-gate-followups.yml`, `agents-verifier.yml`, `pr-00-gate.yml`, `AGENTS.md`, `CLAUDE.md`) instead of the retired `agents-orchestrator.yml` / `agents-pr-meta.yml` pair, with a regression test under `tests/docs/`.

### Fixed
- Integration-Tests sync drift (#1756): `autofix-versions.env` realignment landed via #1971, restoring `maint-69-sync-integration-repo.yml` push success after a 14-day stuck window. The drift detector now passes cleanly.
- Auto-pilot workflow now creates PRs automatically when `agents:auto-pilot` label is added. Previously, the issue intake workflow was forcing "invite" mode for issue events, causing branch creation without PR creation. Fixed by adding `force_mode: true` to the reusable workflow call, allowing the `mode: "create"` parameter to be respected even for issue-triggered events. This resolves the issue where users had to manually create PRs despite auto-pilot being enabled.

### Breaking changes
- None. Breaking changes will be prefixed with **BREAKING** and scheduled in line with the compatibility policy.

## [1.0.0] - 2024-12-16

### Added

#### Workflows (36 files)
- **CI Workflows**: `ci-python`, `ci-cosmetic`, `ci-gate`
- **Health Checks**: `health-40-*` through `health-50-*` (8 workflows)
- **Maintenance**: `maint-45-*` through `maint-60-*` (10 workflows)
- **Agent Orchestration**: `agents-*` (11 workflows)
- **Reusable Workflows**: Python CI, Docker CI, autofix, agents, issue bridge

#### Composite Actions (12)
- `autofix/` - Automated code formatting
- `python-setup/` - Python environment setup
- `coverage-delta/` - Coverage tracking
- `keepalive-gate/` - Keepalive validation
- And 8 more supporting actions

#### Scripts
- 49 helper scripts in `.github/scripts/`
- 19 standalone tools in `scripts/`
- Validation system: `check_branch.sh`, `dev_check.sh`, `validate_fast.sh`

#### Tests (316 total)
- 128 JavaScript tests
- 188 Python tests
- Comprehensive test fixtures for keepalive, agents, orchestrator

#### Documentation (63 files)
- CI system documentation
- Keepalive system guides
- Workflow templates and examples
- Archive of planning documents

#### Infrastructure
- Pre-commit hooks (black, ruff, yaml validation)
- Devcontainer configuration
- Issue templates (6 templates)

### Notes

This is the initial release of the standalone workflow system.
The system is designed to be reusable across multiple consumer repositories.
