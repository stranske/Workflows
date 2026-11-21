# Archived Plans and Audit Reports (updated 2026-11-18)

This ledger records superseded plans, point-in-time audits and historical keepalive records. Compatibility stubs remain for the archived plans and workflow audits that had former `docs/` paths.

For retired GitHub workflows, see [`ARCHIVE_WORKFLOWS.md`](ARCHIVE_WORKFLOWS.md).

## Historical Actionlint references

The [workflow guide](../ci/WORKFLOW_SYSTEM.md) links to the manual for the Actionlint version used by Health 42 and Maint 52. Six copies formerly under `docs/archive/plans/` can be recovered from Git.

| Original revision | Filenames |
| --- | --- |
| `1785424766b30b8860d2a6a2f8d8bf71c4847058` | `actionlint-usage.md` |
| `e1c4da427cbc9081a154bcab10d300001cb8ef7c` | `actionlint-api.md`, `actionlint-checks-reference.md`, `actionlint-config.md`, `actionlint-install-reference.md`, `actionlint-reference.md` |

For example, `git show e1c4da427cbc9081a154bcab10d300001cb8ef7c:docs/archive/plans/actionlint-checks-reference.md` prints the original checks reference.

## Historical dependency enforcement workflow

Use the [consumer maintenance guide](../ops/CONSUMER_REPO_MAINTENANCE.md) for current test dependency checks and lock regeneration. Recover the superseded `DEPENDENCY_WORKFLOW.md` from the original revision:

```sh
git show e1c4da427cbc9081a154bcab10d300001cb8ef7c:docs/archive/plans/DEPENDENCY_WORKFLOW.md
```

## Historical dependency validation rollout

The [development history](../HISTORY.md) records the imported Trend Analysis
Project test counts under **Imported dependency validation rollout**. Both
13,700-byte versions of the former `plans/DEPENDENCY_MANAGEMENT_SUMMARY.md`
are available through Git.

| Version | Commit | SHA-256 |
|---|---|---|
| December 2025 import | `1785424766b30b8860d2a6a2f8d8bf71c4847058` | `1d539211b948a873ff831b8e0da3cb3859dd4a24df8182eeeb4165942ecb9316` |
| Revised Python references | `37d5956b38b8a976820ebaaf3229ff203fbc60cf` | `23cf71277a9cbf6bd2e20c97f75ebee441d11849c0eea55c2c009350f849658d` |

To recover either version, use its commit in
`git show <commit>:docs/archive/plans/DEPENDENCY_MANAGEMENT_SUMMARY.md`.

## Archived January 2026 plans

| Former path | Archive path | Superseded by |
|-------------|--------------|---------------|
| `docs/plans/SHORT_TERM_PLAN.md` | [`plans/SHORT_TERM_PLAN.md`](plans/SHORT_TERM_PLAN.md) | [`docs/ci/WORKFLOW_SYSTEM.md`](../ci/WORKFLOW_SYSTEM.md), [`docs/validation/overview.md`](../validation/overview.md) |
| `docs/plans/LONG_TERM_PLAN.md` | [`plans/LONG_TERM_PLAN.md`](plans/LONG_TERM_PLAN.md) | [`docs/ci/WORKFLOW_SYSTEM.md`](../ci/WORKFLOW_SYSTEM.md), keepalive docs |

## Historical short-term plan briefing

The January 2026 briefing records the addition of eight missing agent labels
in Workflows. It lists Manager-Database issues #227–230 as planned test
deliverables, with 12 Phase 3 functional tests and one Phase 4E test. It
reports 129 passing unit tests for the Phase 3 scripts at that point.

The [full archived short-term plan](plans/SHORT_TERM_PLAN.md) records the
eventual results, including the 12 Phase 3 tests executed on January 10 under
Manager-Database issues #236–248. The [original summary page](../plans/SHORT_TERM_PLAN_SUMMARY.md)
links to the full historical briefing at three revisions. For current
navigation, see the [workflow system guide](../ci/WORKFLOW_SYSTEM.md) and
[validation overview](../validation/overview.md).

## Workflow audit reports

Historical snapshots from the December 2025–January 2026 audit cycle. Monthly operators should follow [`docs/ci/WORKFLOW_AUDIT_PROCEDURE.md`](../ci/WORKFLOW_AUDIT_PROCEDURE.md) and the active workflow catalog instead of these reports.

| Former path | Archive path |
|-------------|--------------|
| `docs/WORKFLOW_AUDIT_2025-12-25.md` | [`audits/WORKFLOW_AUDIT_2025-12-25.md`](audits/WORKFLOW_AUDIT_2025-12-25.md) |
| `docs/WORKFLOW_AUDIT_2026-01-09.md` | [`audits/WORKFLOW_AUDIT_2026-01-09.md`](audits/WORKFLOW_AUDIT_2026-01-09.md) |

## January 2026 Template handoff

- [Template repository evaluation](audits/TEMPLATE_REPO_EVALUATION.md) records the January 3 documentation handoff and links its PR and receiving issue. For current setup and architecture, use the [consumer README](../../templates/consumer-repo/README.md) and [keepalive guide](../keepalive/GoalsAndPlumbing.md).

## Historical verifier evidence

- [Issue #3060 verifier evidence](audits/issue-3060-verifier-evidence.md) preserves the record from Workflows #3095 (`c8ed75938ef1c0ec6ca182aa3803c1ffadf12fe0`). Workflows #3060 closed as completed after source PR #3083 merged (`26f9bb909b47d7d83d93d9f72fa984a7cbe8c3ac`). The August 16 verifier recorded **CONCERNS**. Receiving PR `stranske/Trend_Model_Project#5819` closed without merging.

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
