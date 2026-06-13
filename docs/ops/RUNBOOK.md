# Workflows Operations Runbook

Use this page as the first stop when a PR, agent lane, sync job, or consumer
bootstrap path is stuck. Deeper references remain in the linked source docs.

## Gate Stuck Or Red

1. Open the PR and read the latest `Gate / gate` check plus the Gate summary
   comment.
2. If Gate is waiting on heavy jobs, inspect `python ci`, `docker smoke`, and
   `summary` in `.github/workflows/pr-00-gate.yml`.
3. If the PR is docs-only, confirm the Gate detect job marked `doc_only=true`
   and that heavy jobs were skipped intentionally.
4. If Gate failed because an upstream reusable job failed, use
   [`docs/ci/WORKFLOWS.md`](../ci/WORKFLOWS.md) to find the workflow file and
   rerun or patch the underlying job.

Related docs:

- [`docs/ci/WORKFLOW_SYSTEM.md`](../ci/WORKFLOW_SYSTEM.md)
- [`docs/ci/WORKFLOWS.md`](../ci/WORKFLOWS.md)
- [`docs/keepalive/KEEPALIVE_TROUBLESHOOTING.md`](../keepalive/KEEPALIVE_TROUBLESHOOTING.md)

## Keepalive Not Progressing

1. Confirm the PR is open, non-draft, and has exactly one concrete
   `agent:<name>` label plus `agents:keepalive`.
2. Confirm the branch prefix matches `.github/agents/registry.yml`
   (`codex/issue-*` for `agent:codex`, `claude/issue-*` for `agent:claude`).
3. Check the latest `agents-keepalive-loop.yml` run and the keepalive summary
   comment for the selected next task.
4. If the runner should retry, apply `agent:retry`; the loop removes it at the
   top of the resulting run.
5. Do not wake CLI-agent keepalive PRs with UI-agent comments. The loop is
   workflow-driven and conflicting comments can start the wrong agent surface.

Related docs:

- [`docs/keepalive/Agents.md`](../keepalive/Agents.md)
- [`docs/keepalive/MULTI_AGENT_ROUTING.md`](../keepalive/MULTI_AGENT_ROUTING.md)
- [`docs/keepalive/KEEPALIVE_TROUBLESHOOTING.md`](../keepalive/KEEPALIVE_TROUBLESHOOTING.md)

## Agent Rate-Limited

1. Look for `agent:rate-limited` and the keepalive summary comment.
2. Check whether the PR still has the matching concrete `agent:<name>` label and
   `agents:keepalive`.
3. If the backoff window has cleared, add `agent:retry`.
4. If the same agent remains capacity-stuck after repeated attempts, escalate to
   the closer or workflow-health lane before changing routing labels.

## Sync Drift

1. For consumer template drift, inspect `health-68-consumer-sync-drift.yml` and
   `maint-68-sync-consumer-repos.yml`.
2. For integration repo drift, inspect `health-67-integration-sync-check.yml`
   and `maint-69-sync-integration-repo.yml`.
3. For labels documentation drift, inspect `maint-65-sync-label-docs.yml`.
4. Confirm `.github/sync-manifest.yml` lists every exact-sync file before
   pushing template or workflow changes.

## Consumer Bootstrap

1. Start with the canonical checklist:
   [`templates/consumer-repo/docs/SETUP_CHECKLIST.md`](../../templates/consumer-repo/docs/SETUP_CHECKLIST.md).
2. Use `maint-83-bootstrap-consumer.yml` for repository settings that can be
   safely applied through the GitHub API.
3. Confirm required repository variables, secrets, branch protection, and
   workflow permissions before enabling agent PR automation.
4. Validate a new consumer with Gate, keepalive, verifier, and sync-drift
   smoke paths before treating it as production-ready.

## Known Workflow-Number Collisions

These filename prefixes are currently claimed by more than one live workflow.
Do not infer uniqueness from the numeric prefix alone.

| Prefix | Files |
| --- | --- |
| `agents-72` | `agents-72-codex-belt-worker.yml`, `agents-72-codex-belt-worker-dispatch.yml` |
| `maint-52` | `maint-52-validate-workflows.yml`, `maint-52-sync-dev-versions.yml` |
| `maint-69` | `maint-69-sync-integration-repo.yml`, `maint-69-sync-labels.yml` |
| `maint-71` | `maint-71-auto-fix-integration.yml`, `maint-71-merge-sync-prs.yml` |
| `health-40` | `health-40-repo-selfcheck.yml`, `health-40-sweep.yml` |

Renumbering these files is intentionally out of scope for this runbook.
