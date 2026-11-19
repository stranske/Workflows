# Monthly Workflow Health Audit

**Maint 66:** [`.github/workflows/maint-66-monthly-audit.yml`](../../.github/workflows/maint-66-monthly-audit.yml)

**Schedule:** First day of each month (06:00 UTC cron). Manual `workflow_dispatch` supported.

## What the workflow does

1. Collects workflow-run statistics for the lookback window (default 30 days).
2. Runs the API wrapper guard report.
3. Creates or updates a single open issue labeled `workflow-audit` with a checklist.

## Operator checklist

### Critical

- Review workflows with under 50% success rate and fix or retire them.
- Document any retired workflows in [`docs/archive/ARCHIVE_WORKFLOWS.md`](../archive/ARCHIVE_WORKFLOWS.md).

### Standard review

- Review workflows in the 50–80% success band.
- Confirm workflows with no recent runs are still required.
- Note new workflows added during the month in [`docs/ci/WORKFLOWS.md`](WORKFLOWS.md).

### Documentation

- Update [`docs/LABELS.md`](../LABELS.md) if label triggers changed.
- Update [`docs/WORKFLOW_GUIDE.md`](../WORKFLOW_GUIDE.md) when operator procedures change.
- Distribute consumer-facing changes via the normal sync path (do not patch consumers ad hoc).

## Historical audit reports

Point-in-time reports from the 2025–2026 audit cycle are archived:

- Ledger: [`docs/archive/ARCHIVE_PLANS.md`](../archive/ARCHIVE_PLANS.md)
- December 2025 snapshot: [`docs/archive/audits/WORKFLOW_AUDIT_2025-12-25.md`](../archive/audits/WORKFLOW_AUDIT_2025-12-25.md)
- January 2026 follow-up: [`docs/archive/audits/WORKFLOW_AUDIT_2026-01-09.md`](../archive/audits/WORKFLOW_AUDIT_2026-01-09.md)

Stubs at the former `docs/WORKFLOW_AUDIT_*.md` paths redirect to these archives.

## Related

- Workflow catalog: [`docs/ci/WORKFLOWS.md`](WORKFLOWS.md)
- System overview: [`docs/ci/WORKFLOW_SYSTEM.md`](WORKFLOW_SYSTEM.md)
- Maintainer review log: [`docs/workflow-updates/maint-workflow-review-2026-02-22.md`](../workflow-updates/maint-workflow-review-2026-02-22.md) (Maint 66 section)