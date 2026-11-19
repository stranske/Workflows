# Archived Plans and Audit Reports (updated 2026-11-18)

This ledger records superseded planning documents and point-in-time workflow audit reports. Canonical copies live under `docs/archive/plans/` and `docs/archive/audits/`. Compatibility stubs remain at the former paths so historical links keep resolving.

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

## Documents kept active (not archived)

| Path | Reason |
|------|--------|
| `docs/TODO_EXTENDED_AUTOPILOT.md` | Planned implementation work (`agents-auto-pilot-extended.yml` not yet shipped) |
| `docs/REVIEW_EXTENDED_AUTOPILOT.md` | Current design review for extended auto-pilot (2026-02-17) |
| Other files under `docs/plans/` | Independent rollout or upgrade plans still referenced by operators |

## Rollback

To restore a document at its former path, copy the archived file from this tree back over the stub and update this ledger.