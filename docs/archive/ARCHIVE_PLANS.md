# Archived Plans and Audit Reports (updated 2026-11-18)

This ledger records superseded plans, point-in-time audits and historical keepalive records. Compatibility stubs remain for the archived plans and workflow audits that had former `docs/` paths.

For retired GitHub workflows, see [`ARCHIVE_WORKFLOWS.md`](ARCHIVE_WORKFLOWS.md).

## Archived January 2026 plans

| Former path | Archive path | Superseded by |
|-------------|--------------|---------------|
| `docs/plans/SHORT_TERM_PLAN.md` | [`plans/SHORT_TERM_PLAN.md`](plans/SHORT_TERM_PLAN.md) | [`docs/ci/WORKFLOW_SYSTEM.md`](../ci/WORKFLOW_SYSTEM.md), [`docs/validation/overview.md`](../validation/overview.md) |
| `docs/plans/SHORT_TERM_PLAN_SUMMARY.md` | [`plans/SHORT_TERM_PLAN_SUMMARY.md`](plans/SHORT_TERM_PLAN_SUMMARY.md) | Same as short-term plan |
| `docs/plans/LONG_TERM_PLAN.md` | [`plans/LONG_TERM_PLAN.md`](plans/LONG_TERM_PLAN.md) | [`docs/ci/WORKFLOW_SYSTEM.md`](../ci/WORKFLOW_SYSTEM.md), keepalive docs |

## Workflow audit reports

Historical snapshots from the December 2025–January 2026 audit cycle. Monthly operators should follow [`docs/ci/WORKFLOW_AUDIT_PROCEDURE.md`](../ci/WORKFLOW_AUDIT_PROCEDURE.md) and the active workflow catalog instead of these reports.

| Former path | Archive path |
|-------------|--------------|
| `docs/WORKFLOW_AUDIT_2025-12-25.md` | [`audits/WORKFLOW_AUDIT_2025-12-25.md`](audits/WORKFLOW_AUDIT_2025-12-25.md) |
| `docs/WORKFLOW_AUDIT_2026-01-09.md` | [`audits/WORKFLOW_AUDIT_2026-01-09.md`](audits/WORKFLOW_AUDIT_2026-01-09.md) |

## January 2026 Template handoff

- [Template repository evaluation](audits/TEMPLATE_REPO_EVALUATION.md) records the January 3 documentation handoff and links its PR and receiving issue. For current setup and architecture, use the [consumer README](../../templates/consumer-repo/README.md) and [keepalive guide](../keepalive/GoalsAndPlumbing.md).

## Historical keepalive records

- [Branch-Sync Automation Gaps](keepalive/BranchSyncAutomationGaps.md)
- [Gap Assessment](keepalive/GapAssessment.md)
- [Progress Log](keepalive/ProgressLog.md)
- [Sync Checklist](keepalive/SyncChecklist.md)

The former paths under `docs/keepalive/` were retired. The Gap Assessment and Sync Checklist retain their original relative links. Those links predate the move. Use the current [keepalive contract](../keepalive/GoalsAndPlumbing.md) and [observability contract](../keepalive/Observability_Contract.md) for those references, or follow the [operator guide](../agent-automation.md) for current branch-sync recovery.

## Documents kept active (not archived)

| Path | Reason |
|------|--------|
| `docs/TODO_EXTENDED_AUTOPILOT.md` | Planned implementation work (`agents-auto-pilot-extended.yml` not yet shipped) |
| `docs/REVIEW_EXTENDED_AUTOPILOT.md` | Current design review for extended auto-pilot (2026-02-17) |
| Other files under `docs/plans/` | Independent rollout or upgrade plans still referenced by operators |

## Rollback

To restore a document, copy the archived file to its former path and update this ledger.
