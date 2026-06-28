# PR Verification Evidence — Execution Slice Plan

> **Target:** [stranske/Workflows#2564](https://github.com/stranske/Workflows/issues/2564)  
> **Status:** Planning artifact (documentation-only; no runtime behavior change in this commit)  
> **Last inventoried:** 2026-06-27 from files in this repository

## Context

PR verification and downstream evidence in Workflows spans four coupled lanes:

1. **Compare verification** — post-merge LLM rubric runs (`verify:checkbox`, `verify:evaluate`, `verify:compare`) that emit structured verdicts and comparison artifacts.
2. **Gate evidence** — `pr-00-gate.yml` detect outputs, summary artifacts, and post-CI recovery that explain why a PR route skipped, passed, or failed.
3. **Runtime acceptance** — deliberate-break markers, Gate label arming, and merge-lane guards that defer non-CI-verifiable acceptance to the local Orchestrator path.
4. **Durability / outcome evidence** — terminal disposition NDJSON, follow-up ledgers, and fleet durability export that capture whether verification chains resolved post-merge.

This document inventories repo-local surfaces, names known gaps, and decomposes the next verification-evidence improvements into execution-ready slices. Each slice is scoped so a single agent lane can land it without cross-cutting production changes unless the slice explicitly owns that surface.

## Inventory — Existing Verification / Evidence Surfaces

The table below is derived from repository files only (workflows, scripts, contracts, tests, and analysis docs).

| Lane | Primary entry points | Supporting scripts / contracts | Existing tests & analysis |
| --- | --- | --- | --- |
| **Verifier trigger** | `.github/workflows/agents-verifier.yml`, `templates/consumer-repo/.github/workflows/agents-verifier.yml`, `.github/sync-manifest.yml` | Label contract in `docs/LABELS.md`, `templates/consumer-repo/docs/LABELS.md` | `docs/WORKFLOW_GUIDE.md` (verifier section), `tests/test_workflow_guide_verifier_sections.py` |
| **Reusable verifier** | `.github/workflows/reusable-agents-verifier.yml` | `.github/scripts/agents_verifier_context.js`, `.github/scripts/verifier_ci_query.js`, `.github/scripts/verifier_verdict_json.py`, `.github/scripts/verifier_issue_formatter.js`, `scripts/langchain/pr_verifier.py`, `scripts/langchain/verifier_config.py`, `.github/codex/prompts/verifier_acceptance_check.md` | `tests/scripts/test_pr_verifier_{compare,comparison_report,structured_output,infra_detection,fallback,issue_creation,sync_manifest,chain_depth}.py`, `tests/workflows/test_verifier_{verdict_parsing,terminal_disposition}.py`, `.github/scripts/__tests__/agents-verifier-context.test.js`, `.github/scripts/__tests__/verifier-ci-query.test.js`, `docs/analysis/verify-compare-40pr-evaluation-feb-2026.md` |
| **Follow-up / chain** | `.github/workflows/agents-verify-to-new-pr.yml`, `.github/workflows/agents-verify-to-issue-v2.yml`, consumer templates under `templates/consumer-repo/.github/workflows/` | `scripts/langchain/followup_issue_generator.py`, `scripts/create_verifier_labels.py`, `.github/scripts/terminal_disposition.js`, `.github/scripts/terminal_disposition_coverage.js` | `tests/test_followup_issue_generator.py`, `tests/scripts/test_pr_verifier_chain_depth.py`, `.github/scripts/__tests__/terminal-disposition.test.js`, `.github/scripts/__tests__/terminal-disposition-coverage.test.js` |
| **Gate evidence** | `.github/workflows/pr-00-gate.yml`, `.github/workflows/maint-46-post-ci.yml` | `.github/scripts/gate_summary.py`, `tools/post_ci_summary.py`, `scripts/gate_detect_output_diff.py`, `.github/scripts/detect-changes.js` | `tests/scripts/test_gate_detect_output_diff.py`, `tests/workflows/github_scripts/test_gate_summary.py`, `tests/test_post_ci_summary.py`, `tests/workflows/test_maint46_post_ci_sparse_checkout.py` |
| **Runtime acceptance** | `pr-00-gate.yml` (summary label arming), `.github/workflows/agents-73-codex-belt-conveyor.yml`, `.github/workflows/maint-71-merge-sync-prs.yml`, `.github/workflows/reusable-70-orchestrator-main.yml` | `scripts/check_deliberate_break.py`, `.github/scripts/runtime_ac_merge_guard.js`, `docs/keepalive/GoalsAndPlumbing.md` | `tests/scripts/test_check_deliberate_break.py`, `.github/scripts/__tests__/runtime-ac-merge-guard.test.js` |
| **Terminal disposition & metrics** | Verifier and follow-up workflows upload NDJSON disposition artifacts | `.github/scripts/terminal_disposition.js`, `scripts/aggregate_agent_metrics.py`, `.github/workflows/agents-weekly-metrics.yml` | `tests/workflows/test_verifier_terminal_disposition.py`, `tests/workflows/test_bot_comment_handler.py`, `tests/scripts/test_aggregate_agent_metrics.py`, `tests/workflows/test_workflow_agents_consolidation.py` |
| **Durability / fleet** | `.github/workflows/maint-85-keepalive-durability-export.yml` | `scripts/export_keepalive_durability.py`, `scripts/langsmith_fleet.py`, `scripts/langsmith_fleet_conformance.py`, `docs/contracts/langsmith-fleet-v1.md`, `config/langsmith_fleet_registry.json` | `tests/scripts/test_export_keepalive_durability.py`, `tests/scripts/test_langsmith_fleet.py`, `tests/scripts/test_langsmith_fleet_conformance.py`, `tests/workflows/test_langsmith_fleet_conformance_workflow.py` |
| **Contract-level evidence** | `.github/workflows/reusable-backplane-conformance.yml`, `.github/workflows/health-78-backplane-contract.yml` | `docs/contracts/research-backplane-contract.md`, `docs/contracts/run-contract-v1.md`, `docs/contracts/schemas/evidence-object-v1.schema.json`, `scripts/validate_run_contract.py`, `config/backplane_participants.json` | Contract validation via health workflows; no verifier→evidence-object bridge yet |
| **Operational / reverification docs** | — | `docs/verification-concerns-1307.md`, `docs/reverification/README.md`, `docs/reverification/1307-missing-artifacts.md` | `tests/docs/test_verification_concerns_1307.py` |

### Local artifact surfaces (verifier run workspace)

| File / artifact family | Producer | Uploaded today? | Notes |
| --- | --- | --- | --- |
| `verifier-context.md`, `verifier-diff-summary.md`, `verifier-pr-diff.patch` | `.github/scripts/agents_verifier_context.js` | **No** (written locally; not in upload steps) | Gap documented in `docs/verification-concerns-1307.md` |
| `codex-output.md`, `evaluation.json` | `reusable-agents-verifier.yml` checkbox/evaluate steps | Partial (hashed into disposition; not always uploaded standalone) | Used by terminal disposition concerns hash |
| `comparison.json`, `comparison-comment.md` | compare mode in `reusable-agents-verifier.yml` | Yes (`comparison-results-*`, 7-day retention) | |
| `agent-metrics/verifier-terminal-disposition.ndjson`, `verifier-followup-ledger.ndjson` | terminal disposition step | Yes (`verifier-terminal-disposition-*`, 14-day retention) | |
| `verifier-metrics.ndjson` | metrics collector | Yes (`agents-verifier-metrics`, 30-day retention) | |

### Known gaps (inputs to slices below)

- `docs/verification-concerns-1307.md` and `docs/reverification/1307-missing-artifacts.md` document missing or empty verifier context artifacts that block acceptance-criteria review.
- `docs/analysis/verify-compare-40pr-evaluation-feb-2026.md` recommends persisting `chain_depth` on follow-up artifacts and feeding prior iteration summaries into `followup_issue_generator.py` Round 1.
- `scripts/gate_detect_output_diff.py` validates detect-job output wiring but is not yet wired into Gate CI as a required check.
- Runtime acceptance evidence lives in the local Orchestrator path; Workflows only arms labels and merge guards — there is no repo-local artifact proving a runtime AC spec passed.
- Verifier outputs are not projected into `evidence-object/v1` or cross-linked in a single route-coverage ledger (`docs/contracts/run-contract-v1.md` is opt-in and not wired to verifier yet).

---

## Execution Slices

### Slice 1 — Verifier artifact completeness and replay contract

| Field | Detail |
| --- | --- |
| **Task type** | `feature` (evidence contract hardening) |
| **Problem** | Post-merge verification can finish with verdict comments but leave no durable, machine-readable context bundle when context extraction or diff summarization fails. |
| **Likely touched paths** | `.github/workflows/reusable-agents-verifier.yml`, `.github/scripts/agents_verifier_context.js`, `scripts/langchain/pr_verifier.py`, `scripts/langchain/verifier_config.py`, `.github/sync-manifest.yml`, `templates/consumer-repo/.github/workflows/agents-verifier.yml`, `docs/LABELS.md` |
| **Acceptance criteria** | 1) Every non-skipped verifier run uploads a minimum artifact set: context summary, diff summary (or explicit empty marker with reason), and `evaluation.json` when LLM modes run. 2) Missing required artifacts downgrade the posted verdict to CONCERNS with a stable reason code. 3) Unit/workflow tests assert artifact presence rules without live LLM calls. 4) Consumer template and sync manifest updated if new artifact paths are added. |
| **Validation command** | `pytest tests/workflows/test_verifier_terminal_disposition.py tests/scripts/test_pr_verifier_structured_output.py tests/scripts/test_verifier_config.py -q` |
| **Non-goals** | Changing compare-mode prompts or model slots; re-enabling automatic follow-up issue creation; modifying Gate detect routing. |

### Slice 2 — Gate detect and summary evidence backfill

| Field | Detail |
| --- | --- |
| **Task type** | `feature` (CI guard + test backfill) |
| **Problem** | `scripts/gate_detect_output_diff.py` can detect invalid `jobs.detect.outputs` references, but Gate CI does not fail when detect outputs drift; summary/recovery routes lack a single audit trail for skip/pass/fail decisions. |
| **Likely touched paths** | `.github/workflows/pr-00-gate.yml`, `scripts/gate_detect_output_diff.py`, `.github/scripts/gate_summary.py`, `tools/post_ci_summary.py`, `.github/workflows/maint-46-post-ci.yml`, `templates/consumer-repo/.github/workflows/pr-00-gate.yml`, `templates/consumer-repo/tools/post_ci_summary.py`, `tests/scripts/test_gate_detect_output_diff.py`, `tests/workflows/github_scripts/test_gate_summary.py`, `tests/test_post_ci_summary.py`, `tests/workflows/test_maint46_post_ci_sparse_checkout.py`, `docs/ci/WORKFLOWS.md` |
| **Acceptance criteria** | 1) Gate (or a cheap PR leg) runs `gate_detect_output_diff.py` against a committed baseline for Workflows' `pr-00-gate.yml`. 2) Detect output key additions/removals require an intentional baseline update with test coverage. 3) Summary tests cover doc-only, no-Python, CI failure, Docker skip/run, and coverage payload present/missing cases. 4) Maint 46 recovery tests prove skip-when-summary-succeeded and preview-when-recovery-required. 5) No change to required Gate status names or branch protection. |
| **Validation command** | `pytest tests/scripts/test_gate_detect_output_diff.py tests/workflows/github_scripts/test_gate_summary.py tests/test_post_ci_summary.py tests/workflows/test_maint46_post_ci_sparse_checkout.py -q` |
| **Non-goals** | Rewriting `detect-changes.js` logic; enforcing the same baseline on consumer repos in this slice; making coverage a hard gate beyond current policy. |

### Slice 3 — Verify:compare chain-depth and iteration evidence

| Field | Detail |
| --- | --- |
| **Task type** | `feature` (follow-up pipeline) |
| **Problem** | Follow-up chains re-verify without structured memory of prior iterations; `chain_depth` is consumed in prompts but not consistently persisted on follow-up artifacts, contributing to repeated concerns (40-PR evaluation). |
| **Likely touched paths** | `scripts/langchain/followup_issue_generator.py`, `scripts/langchain/pr_verifier.py`, `.github/workflows/agents-verify-to-new-pr.yml`, `.github/workflows/reusable-agents-verifier.yml`, `tests/scripts/test_pr_verifier_chain_depth.py`, `tests/test_followup_issue_generator.py` |
| **Acceptance criteria** | 1) Follow-up artifacts include `chain_depth` and a bounded list of prior non-PASS summaries. 2) Verifier context builder passes depth into `pr_verifier.py` for follow-up PRs. 3) Round 1 analyze prompt in `followup_issue_generator.py` de-duplicates tasks already addressed in prior iterations. 4) Tests cover depth 0, depth N, and missing-history fallback without live LLM calls. |
| **Validation command** | `pytest tests/scripts/test_pr_verifier_chain_depth.py tests/test_followup_issue_generator.py -q` |
| **Non-goals** | Auto-merging follow-up PRs; changing verify label semantics; altering auto-pilot dispatch policy or chain-depth cap. |

### Slice 4 — Runtime acceptance evidence bridge

| Field | Detail |
| --- | --- |
| **Task type** | `feature` (merge-guard evidence + docs) |
| **Problem** | Runtime AC labels block external auto-merge via `runtime_ac_merge_guard.js`, but Workflows lacks a repo-local, attributable record that a runtime spec actually passed. |
| **Likely touched paths** | `.github/scripts/runtime_ac_merge_guard.js`, `scripts/check_deliberate_break.py`, `.github/workflows/pr-00-gate.yml`, `.github/workflows/agents-73-codex-belt-conveyor.yml`, `.github/workflows/maint-71-merge-sync-prs.yml`, `docs/keepalive/GoalsAndPlumbing.md`, `docs/LABELS.md`, consumer copies under `templates/consumer-repo/` |
| **Acceptance criteria** | 1) Document the handoff contract between Gate label application and Orchestrator runtime acceptance (marker file names, comment markers, or PR body sections). 2) Add a lightweight, non-blocking evidence upload or comment marker schema recording runtime AC disposition without secrets or local-only paths. 3) Merge guards continue to block when evidence is missing or stale. 4) Deliberate-break and runtime AC guard tests cover PASS, blocked, and no-op label cases. |
| **Validation command** | `pytest tests/scripts/test_check_deliberate_break.py -q && node --test .github/scripts/__tests__/runtime-ac-merge-guard.test.js` |
| **Non-goals** | Running Orchestrator inside GitHub Actions; weakening runtime AC merge blocks; implementing the local runtime AC executor in this repo. |

### Slice 5 — Follow-up outcome and terminal disposition evidence

| Field | Detail |
| --- | --- |
| **Task type** | `feature` (workflow/script tests) |
| **Problem** | Terminal disposition and follow-up ledger artifacts exist but route coverage should prove every verifier terminal state maps to exactly one disposition and one follow-up policy action. |
| **Likely touched paths** | `.github/workflows/agents-verify-to-issue-v2.yml`, `.github/workflows/agents-verify-to-new-pr.yml`, `.github/scripts/terminal_disposition.js`, `.github/scripts/terminal_disposition_coverage.js`, `scripts/langchain/verifier_config.py`, `tests/scripts/test_verifier_config.py`, `tests/scripts/test_aggregate_agent_metrics.py`, `tests/workflows/test_workflow_agents_consolidation.py` |
| **Acceptance criteria** | 1) Terminal artifact detection rejects partial repair output and accepts terminal JSON, comparison, and disposition payloads. 2) `verify:create-issue` and `verify:create-new-pr` record terminal disposition artifacts for success, no follow-up, and needs-human outcomes. 3) Chain depth records include current depth, max depth, next depth when applicable, and policy action. 4) Weekly metric aggregation can count verifier dispositions without live GitHub data. |
| **Validation command** | `pytest tests/scripts/test_verifier_config.py tests/scripts/test_aggregate_agent_metrics.py tests/workflows/test_workflow_agents_consolidation.py -q && node --test .github/scripts/__tests__/terminal-disposition.test.js .github/scripts/__tests__/terminal-disposition-coverage.test.js` |
| **Non-goals** | Making verifier CONCERNS automatically open issues from the reusable verifier; mutating historical metrics artifacts; changing follow-up chain-depth cap. |

### Slice 6 — Durability and fleet outcome rollup (optional follow-on)

| Field | Detail |
| --- | --- |
| **Task type** | `feature` (fleet / metrics evidence) |
| **Problem** | Durability export and verifier terminal disposition capture overlapping post-merge success signals but use different schemas and are not joined for route-coverage reporting. |
| **Likely touched paths** | `scripts/export_keepalive_durability.py`, `.github/scripts/terminal_disposition.js`, `.github/workflows/maint-85-keepalive-durability-export.yml`, `config/langsmith_fleet_registry.json`, `docs/contracts/langsmith-fleet-v1.md`, `tests/scripts/test_export_keepalive_durability.py`, `tests/workflows/test_verifier_terminal_disposition.py` |
| **Acceptance criteria** | 1) Define a Workflows-local join key (repo, PR number, verification run id / chain depth) linking verifier terminal disposition with durability classification when both exist. 2) Registry documents any new operation fields; records remain safe for public artifacts (hashes/refs only). 3) Durability export and verifier uploads remain non-blocking for merge paths. 4) Contract docs state durability is post-merge learning evidence, not a merge gate. |
| **Validation command** | `pytest tests/scripts/test_export_keepalive_durability.py tests/scripts/test_langsmith_fleet_conformance.py tests/workflows/test_verifier_terminal_disposition.py -q` |
| **Non-goals** | Emitting raw prompts or PR bodies into fleet NDJSON; making durability export a required check; changing `langsmith-fleet/v1` schema without migration fixtures. |

---

## Integration Order

Execute slices in this order so each layer can consume stable evidence from the previous one:

```text
Slice 1 (verifier artifact completeness)
    → Slice 3 (chain-depth / iteration memory)
        → Slice 5 (terminal disposition / follow-up ledger)
            → Slice 6 (durability rollup)
Slice 2 (gate detect + summary evidence) — parallel after Slice 1; no hard dependency on 3/5
Slice 4 (runtime AC evidence bridge) — parallel after Slice 1; coordinates with Slice 5 join keys
```

**Rationale:**

1. **Slice 1 first** — downstream slices assume verifier runs leave replayable artifacts.
2. **Slice 3 next** — chain-depth fields depend on consistent evaluation/context artifacts from Slice 1.
3. **Slice 2 in parallel** — protects Gate routing independently; cheap once a detect baseline exists.
4. **Slice 4 in parallel** — documents and surfaces runtime AC proof without blocking compare verification.
5. **Slice 5 after 1+3** — terminal disposition policy needs stable verifier and chain metadata.
6. **Slice 6 last** — rollup needs finalized artifact shapes from Slices 1, 3, and 5.

If a slice changes consumer-facing workflows, scripts, prompts, or docs, integrate the Workflows source change first, then mirror `templates/consumer-repo/`, update `.github/sync-manifest.yml` when scope changes, and run matching template/sync validation before any consumer sync.

---

## Re-decomposition Triggers

Stop the current slice and split it again when any of the following occur during implementation:

| Trigger | Action |
| --- | --- |
| A slice touches **both** reusable workflow behavior **and** consumer sync manifest **and** LangChain prompt logic | Split into (a) Workflows-first implementation with tests, (b) template/sync manifest alignment PR. |
| Slice 2 baseline updates require **consumer** `pr-00-gate.yml` parity | Fork consumer baseline strategy into its own slice; do not block Workflows Gate on fleet-wide gate refactors. |
| Slice 4 requires **Orchestrator repo changes** to emit markers | Pause Slice 4; keep Workflows slice to guard + schema-only; document Orchestrator-side work separately. |
| Slice 5 or 6 join logic needs **live cross-repo PAT** access in CI | Reduce scope to offline fixture join + documented manual export; defer scheduled cross-repo ingest. |
| Any slice adds **required** Gate contexts or merge blockers | Split evidence-only upload (non-blocking) from enforcement (blocking). |
| Test surface exceeds **~6 files / 2 subsystems** (e.g., JS guard + Python exporter + workflow YAML) | Split per subsystem with a thin integration slice that only wires outputs. |
| Acceptance criteria require **live GitHub API access or live LLM calls** for local validation | Split offline fixture coverage from integration smoke; do not gate merge on live calls. |
| Production diff likely exceeds **~250 lines** outside tests and docs | Split by route owner: verifier, Gate, runtime acceptance, follow-up disposition, or durability export. |

---

## Validation — This Planning Document

This artifact satisfies the frozen specification when:

- [x] It exists at `docs/orchestrator/pr-verification-evidence-plan.md` and references repo-specific verification/evidence code paths.
- [x] It defines **six** execution-ready slices with task type, likely touched paths, acceptance criteria, validation commands, and non-goals.
- [x] It includes integration order and explicit re-decomposition triggers.
- [x] It does not change production workflow or script behavior (documentation only).
- [x] It does not add dependencies or create GitHub issues.

**Local completeness check:**

```bash
# Six slice headings
grep -E '^### Slice [0-9]' docs/orchestrator/pr-verification-evidence-plan.md | wc -l

# Spot-check inventoried paths exist
test -f scripts/langchain/pr_verifier.py
test -f scripts/gate_detect_output_diff.py
test -f scripts/export_keepalive_durability.py
test -f .github/scripts/runtime_ac_merge_guard.js
test -f .github/scripts/agents_verifier_context.js
test -f docs/contracts/schemas/evidence-object-v1.schema.json
test -f tests/workflows/github_scripts/test_gate_summary.py
```

---

## Out of Scope for This Document

- Implementing any slice (this file is decomposition-only).
- Pushing consumer sync PRs or editing registered consumer repos directly.
- Changing verify label defaults, model slots, or auto-pilot routing.
- Creating GitHub issues, project board items, or CI required checks.
