# Workflow Audit Report - November 2026

**Generated:** 2026-11-19T15:37:58Z (issue baseline)  
**Audit period:** Last 30 days through generation  
**Follow-up PR:** November audit remediation (`orch/issue-4770`)  
**Source issue:** [#4770](https://github.com/stranske/Workflows/issues/4770)

## Executive summary

| Metric | Count |
|--------|------:|
| Total runs | 141,642 |
| Successful | 96,282 |
| Literal `failure` | 7,071 |
| Other conclusions (skipped, cancelled, neutral, …) | ~38,289 |
| Fleet success rate (success / all runs) | 67% |

The November audit issue mixed **per-run display names** with **stable workflow definitions**, counted skipped and neutral runs in failure denominators, and substring-matched display names for “not run” detection. Those defects inflated the attention list with hundreds of dynamic `run-name` rows and falsely listed active workflows as unrun.

**Remediation in this cycle**

| Item | Disposition |
|------|-------------|
| API wrapper guard (`restore_branch_snapshots.py`) | Already clean on `main` before this PR ([#4811](https://github.com/stranske/Workflows/pull/4811)); `check_api_wrapper_guard.py --all` exits 0 |
| Maint 66 ranking and inventory | Group by `workflow_id` / path; decisive failure rate excludes skipped/neutral; exact path not-run matching; bounded issue sections + full artifact ([#4781](https://github.com/stranske/Workflows/pull/4781) commits cherry-picked) |
| Duplicate Detection (`agents-dedup.yml`) | Sparse checkout omitted `tools/embedding_provider.py`; `semantic_matcher` import failed in CI — fixed in this PR |
| Maint 65 Sync Label Docs | Fixed in [#4842](https://github.com/stranske/Workflows/pull/4842) |
| Maint 47 Disable Legacy Workflows | Retired inert workflow in [#4771](https://github.com/stranske/Workflows/pull/4771); documented in [`ARCHIVE_WORKFLOWS.md`](../ARCHIVE_WORKFLOWS.md) |

**Documentation**

| Surface | Required change |
|---------|-----------------|
| `docs/LABELS.md` | No label trigger changes this cycle |
| `docs/WORKFLOW_GUIDE.md` | No operator procedure changes beyond Maint 47 retirement (already in #4771) |
| Consumer sync | Not required for this audit; ranking fix is Workflows-repo Maint 66 only |

## Non-dynamic workflows below 50% decisive failure rate

Rates below use the **corrected** Maint 66 policy: decisive outcomes = success + failure + timed_out + startup_failure + action_required; attention thresholds apply only when ≥5 decisive outcomes exist. Rows marked *volume noise* were false positives under the pre-fix `success/total` rule with zero literal failures.

| Workflow file | Display name | Issue rate (old) | Root cause / disposition |
|---------------|--------------|------------------|---------------------------|
| `agents-dedup.yml` | Duplicate Detection | 0% (149/149 failures) | **Fixed:** sparse checkout missing `tools/embedding_provider.py` → `ModuleNotFoundError` for `semantic_matcher` |
| `agents-keepalive-loop-reporter.yml` | Keepalive Loop Reporter | 6% | Mostly non-failure conclusions and branch-protection noise; sample failed run [44951017026](https://github.com/stranske/Workflows/actions/runs/44951017026): `Resolve reporter target` HTTP 403 `API rate limit exceeded for installation` — external API budget, no repo-local script bug reproduced |
| `maint-46-post-ci.yml` | Maint 46 Post CI | 26% | High volume of real `failure` conclusions on post-Gate housekeeping; sample failed run [44951684191](https://github.com/stranske/Workflows/actions/runs/44951684191): `Gate failure issue and snapshot` HTTP 403 `API rate limit exceeded for installation` — transient external API budget, no code change this PR |
| `health-68-consumer-sync-drift.yml` | Health 68 Consumer Sync Drift | 34% | Consumer drift signal; fix via Maint 68 sync path, not ad hoc consumer patches |
| `agents-63-issue-intake.yml` | Agents 63 Issue Intake | 13% | Event-shape skips and provider routing; failures correlate with held/suspicious-workflow era — monitor |
| `maint-sync-env-from-pyproject.yml` | Maint - Sync pyproject from versions.env | 7% (12/13 failures) | Small sample; manual/version-sync utility — keep, re-check after next scheduled run |
| `pr-46-dependency-repair-contract.yml` | PR 46 Dependency Repair Contract | 4% (7 failures / 4364 runs) | Mostly skipped/cancelled runs; low decisive failure rate — *volume noise* under old rule |
| `health-40-repo-selfcheck.yml` | Health 40 Repo Selfcheck | 25% (3/4) | PAT/admin limits on branch-protection enforcement (same class as prior audits) — external permissions |
| `health-41-repo-health.yml` | Health 41 Repo Health | 25% (3/4) | Same as Health 40 |
| `maint-65-sync-label-docs.yml` | Maint 65 Sync Label Docs | 0% (4/4 failures) | **Fixed** in #4842 |
| `agents-verifier.yml` | Agents Verifier | 14% (1/597) | Single failure in window; keep |
| `agents-auto-label.yml` | Auto-Label Issues | 2% (0 failures) | Skipped-heavy — *volume noise* |
| `maint-71-auto-fix-integration.yml` | Auto-Fix Integration Test Failures | 0% (0 failures) | Skipped-heavy — *volume noise* |
| `agents-verify-to-issue-v2.yml` | Create Issue from Verification (Enhanced) | 0% | Skipped — *volume noise* |
| `agents-verify-to-new-pr.yml` | Create New PR from Verification | 0% | Skipped — *volume noise* |
| `agents-debug-issue-event.yml` | Agents Debug Issue Event | 0% | On-demand diagnostic — *volume noise* |
| `agents-capability-check.yml` | Capability Check | 14% (0 failures) | Skipped — *volume noise* |
| `agents-decompose.yml` | Task Decomposition | 0% | Skipped — *volume noise* |
| `maint-auto-label-dep-prs.yml` | Auto-label dependency PRs | 0% | Skipped — *volume noise* |
| `health-83-dependency-sync-efficiency.yml` | Health 83 Dependency Sync Efficiency | 0% (1 failure) | Campaign-scoped display names — monitor |

**Dynamic display names** (`Merge Sync PRs [campaign]`, `Verifier PR #…`, `keepalive-dispatch/…`, `Agents Issue Optimizer #…`, `Maint 68 canary …`, `npm_and_yarn …`) are not separate workflows. They must not receive independent disposition rows; Maint 66 now aggregates them under their workflow definition.

**Historical optimizer issues** `#4623`, `#4413`, `#4437`, `#4400`, `#4432`, `#4393` remain closed per non-goals.

## Workflows in the 50–80% band (non-dynamic)

| Workflow file | Notes |
|---------------|-------|
| `pr-00-gate.yml` | 62% success / 304 failures — expected mix of cancellations and matrix variance; Gate remains primary CI orchestrator |
| `health-74-template-drift.yml` | 73% — template drift signal; continue via sync/Maint 68 |
| `health-78-backplane-contract.yml` | 66% — contract checks on smaller sample |
| `maint-52-sync-dev-versions.yml` | 78% — periodic version sync |
| `health-85-ci-time-budget.yml` | 65% — advisory timing; delivery evidence tracked separately (#4284, #4769) |
| `agents-71-codex-belt-dispatcher.yml` | 72% — reusable dispatch surface |
| `maint-66-monthly-audit.yml` | 50% (1/4) | Small sample; ranking fix in this cycle |
| `maint-84-prune-agent-stubs.yml` | 50% (2/4) | Scheduled pruner; needs eligible input for full verification (tracker) |
| `agents-weekly-metrics.yml` | 50% (2/4) | Weekly metrics; low volume |
| `agents-moderate-connector.yml` | 71% (0 failures / 4694 runs) | `issue_comment` trigger fires on every comment; the remainder is skipped/cancelled (latest 200 runs: 185 success, 9 skipped, 6 cancelled) — *volume noise*, keep |
| `agents-keepalive-loop.yml` | 73% (120 failures / 2908 runs) | Sampled failed runs [44950515966](https://github.com/stranske/Workflows/actions/runs/44950515966) (Cursor keepalive: HTTP 403 `API rate limit exceeded for installation`), [44942221029](https://github.com/stranske/Workflows/actions/runs/44942221029) and [44032661429](https://github.com/stranske/Workflows/actions/runs/44032661429) (Claude keepalive agent step exit 1) — external API budget plus agent-run failures; no shared repo-local bug reproduced, monitor |
| `selftest-ci.yml` | 74% (403 failures / 2229 runs) | PR CI catching real PR defects: [44968781532](https://github.com/stranske/Workflows/actions/runs/44968781532) and [44934735017](https://github.com/stranske/Workflows/actions/runs/44934735017) failed Black format check on PR files; [44965411641](https://github.com/stranske/Workflows/actions/runs/44965411641) failed a JavaScript test assertion (plus artifact-list 403) — expected signal, keep |
| `maint-88-verifier-runtime-comparison.yml` | 66% (0 failures / 3 runs) | `workflow_dispatch`-only comparison utility; runs are success or cancelled (3 success, 1 cancelled) — small-sample *volume noise*, keep |

## “Workflows not run” classification

The November issue listed ~100 files as unrun because matching used **quoted `name:` headers and display names** instead of normalized `.github/workflows/<file>.yml` paths. After the Maint 66 fix:

| Class | Examples | Disposition |
|-------|----------|-------------|
| `workflow_call`-only reusable | `reusable-*.yml` and belt workers (19 files; no independent `on:` trigger) | Expected — omitted from not-run after Maint 66 skip logic |
| Reusable with manual dispatch | `health-42-actionlint.yml`, `reusable-10-ci-python.yml` | Keep — may appear in not-run in a quiet window despite `workflow_dispatch` |
| Active with runs in window | `pr-00-gate.yml`, `maint-66-monthly-audit.yml`, `agents-dedup.yml` | **False positive** — fixed by path-based detection |
| Scheduled / manual utilities | `maint-45-cosmetic-repair.yml`, `maint-60-release.yml` | Keep — on-demand or tag-driven |
| Retired this month | `maint-47-disable-legacy-workflows.yml` | **Archived** — #4771 |
| Consumer sync / health spot checks | `health-68-*`, `maint-68-*` preview variants | Keep — campaign/canary naming only affects display |

No additional workflow **files** were archived in this PR beyond Maint 47 (already merged). Remaining removal candidates stay in [`docs/reports/workflows-cleanup-tracker.md`](../../reports/workflows-cleanup-tracker.md).

### Full-path inventory (`scripts/workflow_inventory_audit.py`)

Automated classification of all **129** on-disk workflow files (November 2026 checkout):

| Bucket | Count | Disposition |
|--------|------:|-------------|
| `reusable_call_only` | 19 | Expected zero independent runs — Maint 66 skip |
| `reusable_with_independent_trigger` | 11 | Callable plus `workflow_dispatch` / schedule / PR hooks — keep |
| `scheduled` | 31 | Cron or low-frequency — not-run row often benign |
| `manual_utility` | 9 | `workflow_dispatch`-only utilities — keep |
| `event_driven` | 59 | Push, PR, issue, or `workflow_run` — false positives were path/display-name mismatch |

Regenerate the per-file table with:

```bash
PYTHONPATH=. python scripts/workflow_inventory_audit.py --markdown
```

Confirmed **retirement** this cycle: `maint-47-disable-legacy-workflows.yml` ([#4771](https://github.com/stranske/Workflows/pull/4771)); see [`ARCHIVE_WORKFLOWS.md`](../ARCHIVE_WORKFLOWS.md). No other November “not run” rows were confirmed unused.

## Parallelism, runtime, and caching

| Finding | Impact | Action |
|---------|--------|--------|
| Maint 66 issue body could exceed GitHub limits when listing dynamic names | High noise for operators | Bounded sections + `monthly-audit-details` artifact (this cycle) |
| `agents-dedup.yml` sparse checkout | 100% failure class | Include `tools/embedding_provider.py` (this cycle) |
| Gate / Selftest Python jobs | 322–529s vs 600s budget | Documented in cleanup tracker; Health 85 advisory series continues |
| Duplicate dependency install in reusable CI | Maintenance cost | Prior audit recommendations unchanged; not expanded this cycle |
| pip/uv caching on auxiliary workflows | Medium savings | Deferred — no change requested in #4770 tasks |

## Fixes delivered with this report

1. Cherry-pick Maint 66 ranking, conclusion mix, not-run path matching, and artifact bounds (from draft [#4781](https://github.com/stranske/Workflows/pull/4781)).
2. Extend `agents-dedup.yml` sparse checkout so `scripts.langchain.semantic_matcher` can import `tools.embedding_provider`.
3. Publish this archive report and index it in [`ARCHIVE_PLANS.md`](../ARCHIVE_PLANS.md) and [`WORKFLOW_AUDIT_PROCEDURE.md`](../../ci/WORKFLOW_AUDIT_PROCEDURE.md).

## Validation

```text
python scripts/check_api_wrapper_guard.py --all
→ exit 0, no violations

pytest tests/scripts/test_issue_dedup.py tests/scripts/test_check_api_wrapper_guard.py \
  tests/workflows/test_maint66_monthly_audit_stats.py \
  tests/workflows/test_maint66_monthly_audit_issue_body.py -q -m "not slow"
→ 94 passed

pytest tests/scripts/test_validate_workflow_yaml.py \
  tests/workflows/test_workflows_doc_links_resolve.py -q -m "not slow"
→ 7 passed (includes archive audit acceptance via `test_november_2026_archived_workflow_audit_report`)

pytest tests/docs/test_workflow_audit_2026_11_19.py -q -m "not slow"
→ 5 passed

pytest tests/scripts/test_workflow_inventory_audit.py -q -m "not slow"
→ passed
```

---

*Archived 2026-11-21. Next scheduled Maint 66 run should produce a corrected follow-up issue using workflow-definition statistics.*