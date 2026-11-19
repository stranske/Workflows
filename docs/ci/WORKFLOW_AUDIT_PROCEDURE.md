# Monthly Workflow Health Audit

**Maint 66:** [`.github/workflows/maint-66-monthly-audit.yml`](../../.github/workflows/maint-66-monthly-audit.yml)

**Schedule:** First day of each month (06:00 UTC cron). Manual `workflow_dispatch` supported.

## What the workflow does

1. Collects workflow-run statistics for the lookback window (default 30 days).
2. Runs the API wrapper guard report.
3. Creates or updates a single open issue labeled `workflow-audit` with a checklist.

## Operator checklist

### Critical

- Review workflows with over 50% failed decisive outcomes and investigate small-sample failures.
- Document any retired workflows in [`docs/archive/ARCHIVE_WORKFLOWS.md`](../archive/ARCHIVE_WORKFLOWS.md).

### Standard review

- Review workflows with over 20% through 50% failed decisive outcomes.
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
## Conclusion classification and ranking

Maint 66 groups by stable `workflow_id`, falling back to normalized workflow path,
then an explicitly labeled legacy name when older input has neither. Run display
names do not split one workflow or merge different workflow IDs. Not-run detection
uses exact normalized file paths, not substring matches on display names.

Failure ranking uses `(failure + timed_out + startup_failure + action_required)`
divided by `(success + those failed outcomes)`. `action_required` means blocked
pending action, not a test assertion failure. At least five decisive outcomes are
required for a rate-ranked recommendation; any failures below that sample size
appear separately. Immediate attention is strictly over 50%, review strictly over
20% through 50%, ordered by failure rate then failure count, not volume.

All conclusions are retained in the conclusion mix, including neutral, skipped,
cancelled, stale, missing (`unknown`) and future unrecognized values. These do not
inflate failure rates. The overall success/all-runs statistic remains descriptive,
not an attention trigger. The literal `failure` count remains backward compatible;
`failed_outcomes` explicitly includes the additional actionable conclusions.
Collection window, completeness checks, UTC issue month, API wrapper guard and
publication controls are unchanged; no extra API calls are needed.


### Output bounds and complete detail

The issue shows aggregate conclusion counts, then bounded per-workflow detail.
Each attention category, conclusion mix, and not-run section is limited to 6,000
UTF-8 bytes of complete lines plus an explicit omitted-line count. Ranked failures
beyond the limit are **not dropped**: every complete ranked list and the full
workflow statistics JSON are uploaded as `monthly-audit-details` before rendering
or writing the issue. The issue links to that run's artifact, retained for 90 days;
download it within that window when longer-term historical detail is required.
Artifact upload must succeed before publication. A separate 60,000-byte final-body
guard fails visibly rather than posting a truncated or oversized issue, including
if the API guard report grows unexpectedly. The JSON contains aggregate workflow
counts, not raw run payloads. Uploading this artifact adds a bounded artifact-service
operation but no new Actions inventory queries or model calls.

Summary rows distinguish literal `failure` from the full failed-outcome numerator
and decisive denominator. Null conclusions on non-completed runs are classified as
`pending:<status>`; completed or missing-status nulls remain `unknown`. All such
states remain outside the decisive denominator. Workflow IDs remain the grouping
identity; display labels still use the most recently observed run name.
