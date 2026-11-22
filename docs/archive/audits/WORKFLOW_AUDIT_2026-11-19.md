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

## Non-dynamic workflows below 50% baseline success (evaluated under corrected policy)

Rates below use the **corrected** Maint 66 policy: decisive outcomes = success + failure + timed_out + startup_failure + action_required; attention thresholds apply only when ≥5 decisive outcomes exist. The **Issue rate (old)** column is the **baseline success band** from the pre-fix Maint 66 ranking (`success / all runs`, including skipped and neutral in the denominator). Do not treat those percentages as decisive-failure rates; rows marked *volume noise* were false positives under that baseline with zero literal failures.

| Workflow file | Display name | Issue rate (old) | Root cause / disposition |
|---------------|--------------|------------------|---------------------------|
| `agents-dedup.yml` | Duplicate Detection | 0% (149/149 failures) | **Fixed:** sparse checkout missing `tools/embedding_provider.py` → `ModuleNotFoundError` for `semantic_matcher` |
| `agents-keepalive-loop-reporter.yml` | Keepalive Loop Reporter | 6% (1,378/4,383 failures) | Mostly non-failure conclusions and transient GitHub installation rate limits; monitor after Maint 66 fix — no repo-local script bug reproduced |
| `maint-46-post-ci.yml` | Maint 46 Post CI | 26% (1,380/1,883 failures) | High volume of real `failure` conclusions on post-Gate housekeeping; transient external/API rate limit — document, no code change this PR |
| `health-68-consumer-sync-drift.yml` | Health 68 Consumer Sync Drift Check | 34% (557/5,817 failures) | Consumer drift signal; fix via Maint 68 sync path, not ad hoc consumer patches |
| `agents-63-issue-intake.yml` | Agents 63 Issue Intake | 13% (107/1,020 failures) | Event-shape skips and intentional intake guard on unrouted manual dispatch; monitor |
| `maint-sync-env-from-pyproject.yml` | Maint - Sync pyproject from versions.env | 7% (12/13 failures) | Branch-protection rejection (`GH013`) on direct push to `main`; succeeds when already aligned — keep PR-based landing for pin drift |
| `pr-46-dependency-repair-contract.yml` | PR 46 Dependency Repair Contract | 4% (7/4,364 failures) | Mostly skipped/cancelled runs; low decisive failure rate — *volume noise* under old rule |
| `health-40-repo-selfcheck.yml` | Health 40 Repo Selfcheck | 25% (3/4 failures) | PAT/admin limits on branch-protection enforcement (same class as prior audits) — external permissions |
| `health-41-repo-health.yml` | Health 41 Repo Health | 25% (3/4 failures) | Advisory branch-protection drift signal; newer runs succeed after policy stabilized |
| `maint-65-sync-label-docs.yml` | Maint 65 Sync Label Docs | 0% (4/4 failures) | **Fixed** in #4842 |
| `agents-verifier.yml` | Agents Verifier | 14% (1/597 failures) | Single failure in window; keep |
| `agents-auto-label.yml` | Auto-Label Issues | 2% (0/8,050 failures) | Skipped-heavy — *volume noise* |
| `maint-71-auto-fix-integration.yml` | Auto-Fix Integration Test Failures | 0% (0/4,866 failures) | Skipped-heavy — *volume noise* |
| `agents-verify-to-issue-v2.yml` | Create Issue from Verification (Enhanced) | 0% (0/1,048 failures) | Skipped — *volume noise* |
| `agents-verify-to-new-pr.yml` | Create New PR from Verification | 0% (0/1,048 failures) | Skipped — *volume noise* |
| `agents-debug-issue-event.yml` | Agents Debug Issue Event | 0% (0/619 failures) | On-demand diagnostic — *volume noise* |
| `agents-capability-check.yml` | Capability Check | 14% (0/619 failures) | Skipped — *volume noise* |
| `agents-decompose.yml` | Task Decomposition | 0% (0/619 failures) | Skipped — *volume noise* |
| `maint-auto-label-dep-prs.yml` | Auto-label dependency PRs | 0% (0/414 failures) | Skipped — *volume noise* |
| `health-83-dependency-sync-efficiency.yml` | Health 83 Dependency Sync Efficiency | 0% (1/1 failure; dynamic `[sha256:…]` name in #4770) | Campaign-scoped dynamic `run-name` row in #4770; monitor |

**Dynamic display names** (`Merge Sync PRs [campaign]`, `Verifier PR #…`, `keepalive-dispatch/…`, `Agents Issue Optimizer #…`, `Maint 68 canary …`, `npm_and_yarn …`) are not separate workflows. They must not receive independent disposition rows; Maint 66 now aggregates them under their workflow definition.

**Historical optimizer issues** `#4623`, `#4413`, `#4437`, `#4400`, `#4432`, `#4393` remain closed per non-goals.

## Failed run inspection (T4, `gh run view --log-failed`)

Inspected 2026-11-21 via `gh run list` (last 5–30 runs per file) and `gh run view <id> --log-failed` on representative failures. No additional repo-local script or trigger fixes were required in this PR beyond Maint 66 ranking and `agents-dedup.yml` checkout (see **Fixes delivered**).

| Workflow file | Sample run | Root cause from failed logs | Disposition |
|---------------|------------|------------------------------|-------------|
| `agents-keepalive-loop-reporter.yml` | [44951017026](https://github.com/stranske/Workflows/actions/runs/44951017026) | `Reporter applicability unavailable: API rate limit exceeded for installation` | Transient GitHub API / installation quota; recent window mostly `skipped` when keepalive summary job already ran |
| `maint-46-post-ci.yml` | [44951684191](https://github.com/stranske/Workflows/actions/runs/44951684191) | `HttpError: API rate limit exceeded for installation` in Gate snapshot step | Transient API pressure on post-Gate housekeeping; same workflow succeeding on adjacent Gate runs (e.g. 44955752749) |
| `agents-63-issue-intake.yml` | [44953709513](https://github.com/stranske/Workflows/actions/runs/44953709513) | `Expected exactly one agent:* label; found 0` on issue #4792 | Intentional intake guard for misrouted `workflow_dispatch` without routing labels — not a script defect |
| `maint-sync-env-from-pyproject.yml` | [42622854064](https://github.com/stranske/Workflows/actions/runs/42622854064) | `GH013` / `push declined due to repository rule violations` (direct push to `main`) | Branch-protection policy; workflow succeeds when alignment produces no commit ([43820042751](https://github.com/stranske/Workflows/actions/runs/43820042751)). PR-based landing remains the supported path for pin drift |
| `pr-46-dependency-repair-contract.yml` | — | No `failure` conclusions in the last 50 runs (mostly `skipped`) | Volume noise under legacy success/all-runs ranking |
| `health-40-repo-selfcheck.yml` | [43819301872](https://github.com/stranske/Workflows/actions/runs/43819301872) | `403` updating status-check protection (`Resource not accessible by personal access token`) | Admin PAT / permissions ceiling on branch-protection writes |
| `health-41-repo-health.yml` | [42578814903](https://github.com/stranske/Workflows/actions/runs/42578814903) | Health sweep reports missing `Gate / gate` required check on `main` | Advisory drift signal; not a workflow script error ([43824607161](https://github.com/stranske/Workflows/actions/runs/43824607161) success after policy stabilized) |
| `maint-84-prune-agent-stubs.yml` | [43830898674](https://github.com/stranske/Workflows/actions/runs/43830898674) | Direct `git push` to `main` rejected (`GH013`) | **Already fixed on `main`:** workflow opens `maint/prune-closed-agent-stubs` via `create-pull-request` ([44668751200](https://github.com/stranske/Workflows/actions/runs/44668751200) success) |
| `agents-weekly-metrics.yml` | [41398873782](https://github.com/stranske/Workflows/actions/runs/41398873782) | `Max retries reached` / `HttpError` on `WORKFLOWS_APP` after metrics aggregation | Transient GitHub API; newer runs succeed ([43815934471](https://github.com/stranske/Workflows/actions/runs/43815934471)) |
| `health-78-backplane-contract.yml` | — | No failures in the last 15 runs sampled | Contract checks healthy in current window |
| `health-85-ci-time-budget.yml` | [44296475975](https://github.com/stranske/Workflows/actions/runs/44296475975) | `ERROR: stranske/Orchestrator: measurement unavailable` | External fleet dependency (#4284, #4769); advisory series continues |

## Workflows in the 50–80% band (non-dynamic)

Reconciled against all 13 non-dynamic workflow entries published under **Workflows Requiring Review (50-80% success)** in [#4770](https://github.com/stranske/Workflows/issues/4770):

| Workflow file | Display name | Issue #4770 baseline | Evidence & disposition |
|---------------|--------------|----------------------|------------------------|
| `agents-moderate-connector.yml` | Agents Moderate Connector Comments | 71% (0/4,694 failures) | **Volume noise (keep):** zero failures across all 4,694 baseline runs and 0 failures in the latest 150 runs (`gh run list`: 140 `success`, 8 `skipped`, 1 `cancelled`, 1 in-progress). Non-success runs are expected skip/cancel filters; no workflow defect. |
| `agents-keepalive-loop.yml` | Agents Keepalive Loop | 73% (120/2,908 failures) | **Keep; monitor:** latest 100 runs show 88 `success`, 9 `skipped`, 2 `failure`, 1 in-progress (~2.2% decisive failure rate). Failed-log samples reflect transient GitHub installation rate limits (`Check target PR before pushing` in [44950515966](https://github.com/stranske/Workflows/actions/runs/44950515966)) and external agent CLI exit code 1 (`Run Claude` in [44942221029](https://github.com/stranske/Workflows/actions/runs/44942221029)), not a repo-local workflow defect. |
| `selftest-ci.yml` | Selftest CI | 74% (403/2,229 failures) | **Keep (working as intended):** latest 100 runs show 89 `success`, 7 `cancelled` (`cancel-in-progress: true` on superseded PR pushes), and 4 `failure`. Failed-log samples are genuine PR check catches (`Check Black formatting` in [44968781532](https://github.com/stranske/Workflows/actions/runs/44968781532) and [44934735017](https://github.com/stranske/Workflows/actions/runs/44934735017); `Run JavaScript tests` in [44965411641](https://github.com/stranske/Workflows/actions/runs/44965411641)). |
| `pr-00-gate.yml` | Gate | 62% (304/1,878 failures) | **Keep:** expected mix of PR-push cancellations and legitimate PR test/lint failures; Gate remains primary CI orchestrator. |
| `health-74-template-drift.yml` | Health 74 Template Drift | 73% (358/1,347 failures) | **Keep:** template drift signal; continue via sync/Maint 68. |
| `health-78-backplane-contract.yml` | Backplane Contract Integrity | 66% (52/157 failures) | **Keep:** contract checks on smaller sample; last 15 sampled runs had 0 failures. |
| `maint-52-sync-dev-versions.yml` | Maint 52 Sync Dev Versions | 78% (7/33 failures) | **Keep:** periodic version sync. |
| `health-85-ci-time-budget.yml` | Health 85 CI Time Budget | 65% (5/32 failures) | **Keep:** advisory timing; external measurement dependency tracked separately (#4284, #4769). |
| `agents-71-codex-belt-dispatcher.yml` | Agents 71 Codex Belt Dispatcher | 72% (0/22 failures) | **Volume noise (keep):** reusable dispatch surface with 0 failures in window. |
| `maint-66-monthly-audit.yml` | Maint 66 Monthly Audit | 50% (1/4 failures) | **Fixed in this cycle:** small sample; ranking, dependency provisioning, and inventory-error guards delivered in PR #4884. |
| `maint-84-prune-agent-stubs.yml` | Maint 84 Prune Agent Stubs | 50% (2/4 failures) | **Already fixed on `main`:** scheduled pruner migrated to `create-pull-request` ([44668751200](https://github.com/stranske/Workflows/actions/runs/44668751200) success). |
| `agents-weekly-metrics.yml` | agents-weekly-metrics | 50% (2/4 failures) | **Keep; monitor:** low-volume weekly metrics; transient API retries succeeded in newer run ([43815934471](https://github.com/stranske/Workflows/actions/runs/43815934471)). |
| `maint-88-verifier-runtime-comparison.yml` | Maint 88 Verifier Runtime Comparison | 66% (0/3 failures) | **Volume noise / small sample (keep):** manual `workflow_dispatch` #3904 benchmark; `gh run list` shows 3 `success` ([42421935858](https://github.com/stranske/Workflows/actions/runs/42421935858), [42401537967](https://github.com/stranske/Workflows/actions/runs/42401537967), [39004506855](https://github.com/stranske/Workflows/actions/runs/39004506855)) and 1 manual `cancelled` ([42421695302](https://github.com/stranske/Workflows/actions/runs/42421695302)), 0 failures. |

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

python scripts/validate_workflow_yaml.py
→ All 2 workflow file(s) validated successfully

python scripts/validate_workflow_yaml.py \
  .github/workflows/agents-dedup.yml .github/workflows/maint-66-monthly-audit.yml
→ All 2 workflow file(s) validated successfully

pytest -ra tests/scripts/test_issue_dedup.py \
  tests/scripts/test_check_api_wrapper_guard.py \
  tests/workflows/test_maint66_monthly_audit_stats.py \
  tests/workflows/test_maint66_monthly_audit_issue_body.py \
  tests/scripts/test_validate_workflow_yaml.py \
  tests/workflows/test_workflows_doc_links_resolve.py \
  tests/scripts/test_workflow_inventory_audit.py \
  tests/docs/test_workflow_audit_2026_11_19.py \
  tests/test_issue_4770_acceptance_gates.py
→ 139 passed, 0 skipped
```

---

*Archived 2026-11-21. Next scheduled Maint 66 run should produce a corrected follow-up issue using workflow-definition statistics.*
