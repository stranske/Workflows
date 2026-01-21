# Debouncing Run Count Log

Record workflow run counts before and after debouncing changes. Use
`scripts/workflow_run_counts.py` to produce the comparison table and paste the
output below.

## Latest Measurement

**Status:** needs-human (awaiting workflow concurrency updates + API snapshots)

```text
Workflow  Before  After  Delta  Change
```

## Pending Workflow Concurrency Updates (needs-human)

Agent-standard cannot edit `.github/workflows`. Apply `cancel-in-progress: true`
for the high-frequency workflows below (they either lack concurrency or set
`cancel-in-progress: false`). Run `python scripts/workflow_concurrency_audit.py`
after updates to confirm all `has_canceling_concurrency` entries are true.

| Workflow | Recommended group |
| --- | --- |
| `.github/workflows/agents-auto-pilot.yml` | `${{ github.workflow }}-pr-${{ github.event.pull_request.number || github.ref }}` |
| `.github/workflows/agents-bot-comment-handler.yml` | `${{ github.workflow }}-pr-${{ github.event.pull_request.number || github.ref }}` |
| `.github/workflows/agents-guard.yml` | `${{ github.workflow }}-pr-${{ github.event.pull_request.number || github.ref }}` |
| `.github/workflows/agents-keepalive-loop.yml` | `${{ github.workflow }}-pr-${{ github.event.pull_request.number || github.ref }}` |
| `.github/workflows/agents-moderate-connector.yml` | `${{ github.workflow }}-issue-${{ github.event.issue.number || github.ref }}` |
| `.github/workflows/agents-pr-meta-v4.yml` | `${{ github.workflow }}-pr-${{ github.event.pull_request.number || github.ref }}` |
| `.github/workflows/agents-verifier.yml` | `${{ github.workflow }}-pr-${{ github.event.pull_request.number || github.ref }}` |
| `.github/workflows/agents-verify-to-issue-v2.yml` | `${{ github.workflow }}-pr-${{ github.event.pull_request.number || github.ref }}` |
| `.github/workflows/autofix.yml` | `${{ github.workflow }}-pr-${{ github.event.pull_request.number || github.ref }}` |
| `.github/workflows/health-40-sweep.yml` | `${{ github.workflow }}-pr-${{ github.event.pull_request.number || github.ref }}` |
| `.github/workflows/health-43-ci-signature-guard.yml` | `${{ github.workflow }}-pr-${{ github.event.pull_request.number || github.ref }}` |
| `.github/workflows/health-44-gate-branch-protection.yml` | `${{ github.workflow }}-pr-${{ github.event.pull_request.number || github.ref }}` |
| `.github/workflows/health-50-security-scan.yml` | `${{ github.workflow }}-pr-${{ github.event.pull_request.number || github.ref }}` |
| `.github/workflows/health-70-validate-sync-manifest.yml` | `${{ github.workflow }}-pr-${{ github.event.pull_request.number || github.ref }}` |
| `.github/workflows/health-72-template-sync.yml` | `${{ github.workflow }}-pr-${{ github.event.pull_request.number || github.ref }}` |
| `.github/workflows/health-73-template-completeness.yml` | `${{ github.workflow }}-pr-${{ github.event.pull_request.number || github.ref }}` |
| `.github/workflows/health-keepalive-e2e.yml` | `${{ github.workflow }}-pr-${{ github.event.pull_request.number || github.ref }}` |
| `.github/workflows/maint-52-sync-dev-versions.yml` | `${{ github.workflow }}-${{ github.ref }}` |
| `.github/workflows/maint-52-validate-workflows.yml` | `${{ github.workflow }}-pr-${{ github.event.pull_request.number || github.ref }}` |
| `.github/workflows/maint-60-release.yml` | `${{ github.workflow }}-${{ github.ref }}` |
| `.github/workflows/maint-65-sync-label-docs.yml` | `${{ github.workflow }}-${{ github.ref }}` |
| `.github/workflows/maint-69-sync-integration-repo.yml` | `${{ github.workflow }}-${{ github.ref }}` |
| `.github/workflows/maint-71-auto-fix-integration.yml` | `${{ github.workflow }}-issue-${{ github.event.issue.number || github.ref }}` |
| `.github/workflows/maint-dependabot-auto-label.yml` | `${{ github.workflow }}-pr-${{ github.event.pull_request.number || github.ref }}` |
| `.github/workflows/maint-dependabot-auto-lock.yml` | `${{ github.workflow }}-pr-${{ github.event.pull_request.number || github.ref }}` |
| `.github/workflows/maint-sync-action-versions.yml` | `${{ github.workflow }}-${{ github.ref }}` |
| `.github/workflows/maint-sync-env-from-pyproject.yml` | `${{ github.workflow }}-${{ github.ref }}` |
