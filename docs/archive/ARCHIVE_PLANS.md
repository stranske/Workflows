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

## Superseded workflow plans

The five plans below are available at their original Git revisions. In a
shallow checkout, fetch the listed revision with `git fetch --depth=1 origin <commit>`
before running its recovery command. Use the current references for operational guidance.

| Plan | Recover the original | SHA-256 | Current references |
| --- | --- | --- | --- |
| Autofix workflow | `git show e1c4da427cbc9081a154bcab10d300001cb8ef7c:docs/archive/plans/autofix_workflow_plan.md` | `b74fc5ec27fe4e6b4013d66c991837e47b9900a6f948c0bee4319f340f49f9fa` | See **Autofix routes** in the [workflow catalog](../ci/WORKFLOWS.md). |
| CI reuse consolidation | `git show e1c4da427cbc9081a154bcab10d300001cb8ef7c:docs/archive/plans/ci_reuse_consolidation_plan.md` | `cd6b17268b278ae67927f072c2faf3a7af7c7a90c1e32b6f9b8512c38d8b3ae6` | See the [workflow catalog](../ci/WORKFLOWS.md) and **Scenario Matrix** in the [Selftest guide](../ci/SELFTESTS.md). |
| Reusable agents | `git show e1c4da427cbc9081a154bcab10d300001cb8ef7c:docs/archive/plans/reusable_agents_plan.md` | `f728b26b925b6b13bb0e570d9858e85fbfef2c09dcb673581c21592cd6039d9d` | [Reusable 16 Agents](../../.github/workflows/reusable-16-agents.yml) and [Reusable 70 Orchestrator Main](../../.github/workflows/reusable-70-orchestrator-main.yml) define the current caller inputs. |
| Validation scripts | `git show 1785424766b30b8860d2a6a2f8d8bf71c4847058:docs/archive/plans/validation-scripts.md` | `5044f347f9e876a366b9591f662dbbe96eeb984da6ae2c215e806e675b872245` | See **check_branch.sh - Comprehensive Validation** in the [validation overview](../validation/overview.md) and the [script itself](../../scripts/check_branch.sh). |
| Workflow renaming | `git show e1c4da427cbc9081a154bcab10d300001cb8ef7c:docs/archive/plans/workflow_renaming_plan.md` | `0f46abb8e6f2a33eb688baf15f074112702008065b702fb7a7dde7a646102e56` | See the [workflow catalog](../ci/WORKFLOWS.md) and [workflow naming tests](../../tests/workflows/test_workflow_naming.py). |

## Archived January 2026 plans

| Former path | Archive path | Superseded by |
|-------------|--------------|---------------|
| `docs/plans/SHORT_TERM_PLAN.md` | [`plans/SHORT_TERM_PLAN.md`](plans/SHORT_TERM_PLAN.md) | [`docs/ci/WORKFLOW_SYSTEM.md`](../ci/WORKFLOW_SYSTEM.md), [`docs/validation/overview.md`](../validation/overview.md) |
| `docs/plans/LONG_TERM_PLAN.md` | [`plans/LONG_TERM_PLAN.md`](plans/LONG_TERM_PLAN.md) | [`docs/ci/WORKFLOW_SYSTEM.md`](../ci/WORKFLOW_SYSTEM.md), keepalive docs |

## Historical short-term plan briefing

The January 2026 briefing reports that adding eight missing labels brought
Workflows to 16 agent-related labels. It lists Manager-Database issues #227–230 as planned test
deliverables, with 12 Phase 3 functional tests and one Phase 4E test. It
reports 129 passing unit tests for the Phase 3 scripts at that point.

The [full archived short-term plan](plans/SHORT_TERM_PLAN.md) records the
eventual results, including the 12 Phase 3 tests executed on January 10 under
Manager-Database issues #236–248. The [original summary page](../plans/SHORT_TERM_PLAN_SUMMARY.md)
links to the full historical briefing at three revisions. For current
navigation, see the [workflow system guide](../ci/WORKFLOW_SYSTEM.md) and
[validation overview](../validation/overview.md).

## January Auto-Pilot analysis and metrics proposals

The January design evaluation and deviations summary describe the pipeline at
the time. The remediation plan records options for separating workflow steps,
and the revised scope proposes ways to capture metrics for Workflows #880.
PR #1381 superseded the three January design records with the
[February 40-PR evaluation](../analysis/autopilot-40pr-evaluation-feb-2026.md).
The January proposals include future work whose implementation status is
outside this archive. For current behavior and operations, use the
[workflow catalog](../ci/WORKFLOWS.md), [operator guide](../agent-automation.md),
and [metrics schema](../ci/AUTOPILOT_METRICS_SCHEMA.md).

The four originals share the tree from PR #1381 at
`ed65b8e904cab95cb37c084533cf34b3576344fa`. Browse the
[pinned analysis directory][january-autopilot-tree] to follow their links in
context.

[january-autopilot-tree]: https://github.com/stranske/Workflows/tree/ed65b8e904cab95cb37c084533cf34b3576344fa/docs/analysis

| Original file under `docs/analysis/` | SHA-256 |
| --- | --- |
| `autopilot-design-compliance-evaluation.md` | `5eef1e578d597178d4b2153560a74e7fa544c011f9d96d95bb73ec416e231ec0` |
| `autopilot-deviations-summary.md` | `04f554af61d1e76cd127f61a43b4056b7a72c89a1016e8f616b43cd849a656aa` |
| `autopilot-remediation-plan.md` | `8aeef5a5ff819906dcf6600afee17f1d4a501663de35a33af9e3668cdc1cec37` |
| `issue-880-revised-scope.md` | `8bf48fb8356bceb8e7f0403d2647a0a2db8967921ecf83de9b4658918dbaf237` |

From the root of a Workflows checkout, use Bash to recover all four documents
and their direct relative link targets in a new temporary directory. Compare
the printed checksums with the table.

```bash
(
  set -euo pipefail
  revision=ed65b8e904cab95cb37c084533cf34b3576344fa
  packet=(
    docs/analysis/autopilot-design-compliance-evaluation.md
    docs/analysis/autopilot-deviations-summary.md
    docs/analysis/autopilot-remediation-plan.md
    docs/analysis/issue-880-revised-scope.md
  )
  if ! git cat-file -e "$revision^{commit}" 2>/dev/null; then
    git fetch --depth=1 origin "$revision"
  fi
  destination=$(mktemp -d)
  git archive "$revision" -- "${packet[@]}" \
    docs/analysis/autopilot-40pr-evaluation-feb-2026.md \
    docs/keepalive/GoalsAndPlumbing.md \
    docs/keepalive/METRICS_SCHEMA.md \
    docs/keepalive/MULTI_AGENT_ROUTING.md \
    docs/keepalive/Observability_Contract.md \
    docs/plans/AUTOPILOT_FIX_HISTORY.md \
    docs/plans/SHORT_TERM_PLAN.md \
    .github/workflows/agents-auto-pilot.yml |
    tar -xf - -C "$destination"
  cd "$destination"
  printf 'Recovered in %s\n' "$destination"
  shasum -a 256 "${packet[@]}"
)
```

## Workflow audit reports

Historical snapshots from the December 2025–January 2026 audit cycle. Monthly operators should follow [`docs/ci/WORKFLOW_AUDIT_PROCEDURE.md`](../ci/WORKFLOW_AUDIT_PROCEDURE.md) and the active workflow catalog instead of these reports.

| Former path | Archive path |
|-------------|--------------|
| `docs/WORKFLOW_AUDIT_2025-12-25.md` | [`audits/WORKFLOW_AUDIT_2025-12-25.md`](audits/WORKFLOW_AUDIT_2025-12-25.md) |
| `docs/WORKFLOW_AUDIT_2026-01-09.md` | [`audits/WORKFLOW_AUDIT_2026-01-09.md`](audits/WORKFLOW_AUDIT_2026-01-09.md) |
| `docs/WORKFLOW_AUDIT_2026-11-19.md` | [`audits/WORKFLOW_AUDIT_2026-11-19.md`](audits/WORKFLOW_AUDIT_2026-11-19.md) |

## January 2026 Template handoff

- [Template repository evaluation](audits/TEMPLATE_REPO_EVALUATION.md) records the January 3 documentation handoff and links its PR and receiving issue. For current setup and architecture, use the [consumer README](../../templates/consumer-repo/README.md) and [keepalive guide](../keepalive/GoalsAndPlumbing.md).

## Historical verifier evidence

- [Issue #3060 verifier evidence](audits/issue-3060-verifier-evidence.md) preserves the record from Workflows #3095 (`c8ed75938ef1c0ec6ca182aa3803c1ffadf12fe0`). Workflows #3060 closed as completed after source PR #3083 merged (`26f9bb909b47d7d83d93d9f72fa984a7cbe8c3ac`). The August 16 verifier recorded **CONCERNS**. Receiving PR `stranske/Trend_Model_Project#5819` closed without merging.

## Historical keepalive records

- [Branch-Sync Automation Gaps](keepalive/BranchSyncAutomationGaps.md)
- [Gap Assessment](keepalive/GapAssessment.md)
- [Keepalive Reliability Plan](keepalive/Keepalive_Reliability_Plan.md) records the original design. See the [original revision][keepalive-reliability-original], [current integration guide](../keepalive/Keepalive_Integration.md), and [observability contract](../keepalive/Observability_Contract.md).
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

## Superseded LLM installation handoff

The February handoff recorded how to apply protected workflow edits. For today's
cache and pinned dependencies, see [Auto-Pilot](../../.github/workflows/agents-auto-pilot.yml),
[the issue optimizer](../../.github/workflows/agents-issue-optimizer.yml),
and [the reusable verifier](../../.github/workflows/reusable-agents-verifier.yml).

The three original files are under `docs/workflow-updates/` at revision
`fbb4e424d29f3f51058b247e2be390093dca299d`. On GitHub, browse
`https://github.com/stranske/Workflows/tree/fbb4e424d29f3f51058b247e2be390093dca299d/docs/workflow-updates`.

| Original file | SHA-256 |
| --- | --- |
| `README.md` | `e86c8f659af6173b5f80f92e03f311cde4864f7436956790b2ddaa3a596e2a55` |
| `agents-auto-pilot-changes.yml` | `560efa0e2b1adbc7f73a031047b92822e33538fef6ad94da1725c399f08dff96` |
| `reusable-agents-verifier-changes.yml` | `8545093bc850563898558cd153c1ad20716e521a1e7151729b0c1e63bbca6cb8` |

From a shallow Workflows checkout, choose a filename from the table. Compare
the printed SHA-256 with its listed value. To read the original, omit the pipe
to `shasum`.

```bash
(
  set -euo pipefail
  revision=fbb4e424d29f3f51058b247e2be390093dca299d
  filename=README.md
  git fetch --depth=1 origin "$revision"
  git show "${revision}:docs/workflow-updates/${filename}" | shasum -a 256
)
```

## Historical Python CI plan and January 2026 rate-limit report

The Python CI plan recorded completion of the former `pr-10-ci-python.yml`.
The [current Gate](../../.github/workflows/pr-00-gate.yml) calls the
[reusable Python CI workflow](../../.github/workflows/reusable-10-ci-python.yml).
The January report records API rate-limit incidents and follow-up work as of
that week. Use [Health 75](../../.github/workflows/health-75-api-rate-diagnostic.yml)
for current diagnostics.

Both original documents are available at revision
`3656fdf8d2d934f4da74c7f15361563ce512183a`.

| Original file under `docs/ci/` | SHA-256 |
| --- | --- |
| `pr-10-ci-python-plan.md` | `6983d5aaf988efb119785dd78523b82fa78b43b493fd48b33cf42662d6cb9288` |
| `api-rate-limit-fix-status-2026-01-31.md` | `bad09b1031c89b750575ed6e15213278e16f8f662ef36a0625dd9a3579b14eac` |

To verify either file in a shallow checkout, set `filename` to its name above.
Omit the final pipe to read the document.

```bash
(
  set -euo pipefail
  revision=3656fdf8d2d934f4da74c7f15361563ce512183a
  filename=pr-10-ci-python-plan.md
  git fetch --depth=1 origin "$revision"
  git show "${revision}:docs/ci/${filename}" | shasum -a 256
)
```

[keepalive-reliability-original]: https://github.com/stranske/Workflows/blob/36590718b0222de4cbb27ec7b5a4ddd93dbb3e17/docs/keepalive/Keepalive_Reliability_Plan.md
