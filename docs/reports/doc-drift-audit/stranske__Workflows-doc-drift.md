# stranske/Workflows — Source-of-Truth Doc Drift Audit

> Audit produced for [#2089](https://github.com/stranske/Workflows/issues/2089). Scope: every doc named as a source-of-truth entry point in `CLAUDE.md`, `AGENTS.md`, and `README.md` anchors. Authoritative sources verified by direct `rg` against `.github/workflows/`, `scripts/`, `tools/`, and `.github/agents/registry.yml`. The audit produces this report and follow-up issues only — no inline doc fixes per the issue's Non-Goals.

## Regression-prevention test

`tests/docs/test_workflow_source_docs.py` is the regression-prevention gate for the two highest-blast-radius docs covered here:

- `test_readme_verify_compare_models_match_langchain_defaults` locks `README.md`'s `verify:compare` model identifiers against `tools.langchain_client._default_slots()` and explicitly rejects the prior stale `gpt-5.2 + claude-sonnet-4-5` claim.
- `test_workflows_doc_names_gate_autofix_dispatch_path` locks `docs/ci/WORKFLOWS.md`'s description of the Gate → `agents-autofix-dispatcher.yml` → `agents-autofix-loop.yml` chain against the actual workflow YAML.

`tests/tools/test_langchain_client.py:44` is the model-client test that catches divergence between `_default_slots()` and the verify/compare pipeline.

## Classification table

One row per scoped doc. `accurate` means no mismatches found by the targeted queries described below. `stale` means the doc describes outdated behavior or command. `contradictory` means internal self-contradiction or conflict with implementation. `covered by #N` points to the issue whose PR (filed before this audit) addresses the drift.

| # | Doc | Classification | Specific claim audited | Authoritative source checked | Follow-up issue |
|---|---|---|---|---|---|
| 1 | `README.md` | accurate after [#2085](https://github.com/stranske/Workflows/issues/2085) | Line 77 `verify:compare` model identifiers | `tools/langchain_client.py:96-98` (`_default_slots`); `tests/docs/test_workflow_source_docs.py::test_readme_verify_compare_models_match_langchain_defaults` | resolved by #2085 (PR #2092 merged 2026-05-13) |
| 2 | `docs/INTEGRATION_GUIDE.md` | accurate | Workflow names in "Workflow Summary" and "Legacy Workflow → Replacement" tables (lines 730-750); secrets table (line 757) | `.github/workflows/` (root) for live names; `templates/consumer-repo/.github/workflows/` for `agents-80-pr-event-hub.yml`, `agents-81-gate-followups.yml`, `pr-00-gate.yml` (all present); legacy names in the migration table are documented as replaced, not claimed current | none required |
| 3 | `docs/ops/REPO_REVIEW_PROCESS.md` | accurate after [#2088](https://github.com/stranske/Workflows/issues/2088) | "Weekly Run" Phase-4 entry-point command at lines 52, 65, 71, 89 | `scripts/repo_review_coordinator.py` (present; Phase-4 entry point) and `scripts/repo_review_evaluator.py` (present; preflight). The doc currently names the coordinator as the primary entry point with the evaluator preserved for preflight use — fix from #2088 / PR #2095 (merged 2026-05-14T03:00:45Z) is on `main`. | resolved by #2088 (PR #2095 merged 2026-05-14) |
| 4 | `docs/keepalive/GoalsAndPlumbing.md` | accurate | Agent table row 143: `agent:codex` → "Codex CLI (gpt-5.5; fallback gpt-5.4) → `reusable-codex-run.yml`" | `.github/workflows/reusable-codex-run.yml:63` (`default: 'gpt-5.5'`); `.github/agents/registry.yml` entry for `codex` (runner = `reusable-codex-run.yml`). Other workflow references (Gate, keepalive loop, branch-sync) match `.github/workflows/`. | none required |
| 5 | `docs/AGENTS_POLICY.md` | accurate after [#2098](https://github.com/stranske/Workflows/issues/2098) | "Covered files" now names the same three workflows referenced by the verification checklist: `agents-63-issue-intake.yml`, `agents-70-orchestrator.yml`, and `agents-guard.yml`. | `.github/workflows/agents-guard.yml` exists and is named in the protected workflow list; `.github/scripts/agents-guard.js:12` `DEFAULT_PROTECTED_PATHS = ['.github/workflows/agents-*.yml']` remains the broad runtime guard. | resolved by #2098 (PR #2101 merged 2026-05-14) |
| 6 | `docs/LABELS.md` | stale | Inventory omits `agent:claude`, `agent:auto`, `agent:retry`, `agent:rate-limited` (all actively used) and documents `agent:codex-invite` (no live trigger). LABELS.md is synced to consumer repos via `.github/sync-manifest.yml:636-637`, so the drift propagates fleet-wide. | `.github/agents/registry.yml` (`claude` is a first-class agent); `.github/workflows/agents-keepalive-loop.yml:171-235` (lifecycle for `agent:retry` / `agent:rate-limited`); `.github/workflows/agents-auto-pilot.yml:380-382` (label application); `.github/workflows/agents-auto-label.yml:37-38` (`agent:claude` / `agent:auto`); `grep -rn codex-invite .github/ scripts/ tools/` is empty. | [#2099](https://github.com/stranske/Workflows/issues/2099) |
| 7 | `docs/keepalive/Agents.md` | accurate | Multi-agent claim ("Codex and Claude share the same orchestration surfaces"); required-reading list (`GoalsAndPlumbing.md`, `MULTI_AGENT_ROUTING.md`, `Observability_Contract.md`, `ADD_NEW_AGENT.md`, analysis doc) | `.github/agents/registry.yml` registers both `codex` and `claude` as first-class agents with parallel `runner_workflow`, `branch_prefix`, and capabilities; all required-reading files exist under `docs/keepalive/` and `docs/guides/`. | none required |
| 8 | `docs/ci/WORKFLOWS.md` | contradictory | Line 19 prose correctly says Gate dispatches `autofix_gate_failure` to `agents-autofix-dispatcher.yml`, but the target-layout Mermaid diagram still shows Gate flowing directly to `Reusable 18 Autofix` / `.reusable-18-autofix.yml`. | `.github/workflows/pr-00-gate.yml` dispatches `autofix_gate_failure`; `.github/workflows/agents-autofix-dispatcher.yml:3` listens for the repository dispatch; `agents-autofix-loop.yml` performs the PR autofix iteration. `Reusable 18 Autofix` remains a reusable helper, not the direct Gate target path shown by the diagram. | [#2102](https://github.com/stranske/Workflows/issues/2102) |
| 9 | `docs/MODEL_MANAGEMENT.md` | accurate | Lines 37-48 enumerate model identifiers used in verify/evaluate/compare and progress review. | `tools/langchain_client.py:96-98` (`gpt-5.4`, `claude-sonnet-4-6`); confirmed by `tests/docs/test_workflow_source_docs.py` and `tests/tools/test_langchain_client.py:44`. | none required |
| 10 | `docs/WORKFLOW_GUIDE.md` | accurate | Workflow inventory table (lines 20-23) and per-workflow descriptions (lines 42, 46, 92, 102, 111-114, 122-125, 132, 138-140) | All cited workflows exist in either `.github/workflows/` (root: `pr-00-gate.yml`, `agents-autofix-dispatcher.yml`, `agents-autofix-loop.yml`, `agents-keepalive-*.yml`, `agents-pr-meta-v4.yml`, `agents-verifier.yml`) or `templates/consumer-repo/.github/workflows/` (`agents-80-pr-event-hub.yml`, `agents-81-gate-followups.yml`, `pr-00-gate.yml`). Consumer-vs-Workflows split is consistent with `CLAUDE.md` guidance. | none required |
| 11 | `docs/ops/REPO_REVIEW_ROUND2_PROTOCOL.md` | accurate | Round-2 output paths under `<output_dir>/round2/<repo_safe>/turn-<N>/<agent>.json`; references to `REPO_REVIEW_ROUND2_SCHEMA.md` and `scripts/repo_review_round2_schema.py`. | `scripts/repo_review_round2_schema.py` exists and is invoked by the coordinator; `docs/ops/REPO_REVIEW_ROUND2_SCHEMA.md` exists; `scripts/repo_review_round2_runner.py` exists. | none required |
| 12 | `docs/ops/REPO_REVIEW_ROUND1_SCHEMA.md` | accurate | Output path `<output_dir>/round1/<agent>/<repo_safe>/findings.json` and validator `scripts/repo_review_round1_schema.py::validate_findings(data)`. | `scripts/repo_review_round1_schema.py` exists; `scripts/repo_review_round1_runner.py` exists; the coordinator (`scripts/repo_review_coordinator.py`) reads round-1 findings before round-2 negotiation. | none required |
| 13 | `AGENTS.md` | accurate | Required reading list and "Current consumer default entry points" (line 46): `agents-issue-intake.yml`, `agents-80-pr-event-hub.yml`, `agents-81-gate-followups.yml`, `agents-verifier.yml`, `autofix.yml`, `ci.yml`, `pr-00-gate.yml`. | All 7 cited workflows present in `templates/consumer-repo/.github/workflows/`. Required-reading paths (`docs/WORKFLOW_GUIDE.md`, `docs/ci/WORKFLOWS.md`, `docs/INTEGRATION_GUIDE.md`, `docs/ops/CONSUMER_REPO_MAINTENANCE.md`, `docs/keepalive/Agents.md`, `docs/keepalive/GoalsAndPlumbing.md`) all exist. | none required |

## Summary

- 13 source-of-truth docs audited.
- 2 currently classified `stale` or `contradictory` without a merged fix:
  - `docs/ci/WORKFLOWS.md` target-layout diagram still shows Gate flowing directly to `Reusable 18 Autofix` -> [#2102](https://github.com/stranske/Workflows/issues/2102)
  - `docs/LABELS.md` (stale) -> [#2099](https://github.com/stranske/Workflows/issues/2099)
- 3 previously stale or contradictory docs are accurate on current `main` after already-filed fixes:
  - `README.md` (stale, covered by [#2085](https://github.com/stranske/Workflows/issues/2085))
  - `docs/ops/REPO_REVIEW_PROCESS.md` (stale, covered by [#2088](https://github.com/stranske/Workflows/issues/2088))
  - `docs/AGENTS_POLICY.md` (contradictory, resolved by [#2098](https://github.com/stranske/Workflows/issues/2098) / PR #2101)
- 11 classified `accurate` on current `main`: `README.md`, `docs/INTEGRATION_GUIDE.md`, `docs/ops/REPO_REVIEW_PROCESS.md`, `docs/keepalive/GoalsAndPlumbing.md`, `docs/AGENTS_POLICY.md`, `docs/keepalive/Agents.md`, `docs/MODEL_MANAGEMENT.md`, `docs/WORKFLOW_GUIDE.md`, `docs/ops/REPO_REVIEW_ROUND2_PROTOCOL.md`, `docs/ops/REPO_REVIEW_ROUND1_SCHEMA.md`, `AGENTS.md`.

## Methodology

For each scoped doc, the audit ran three classes of targeted `rg` query, plus direct file reads when needed:

- **Command-name verification:** `rg "repo_review_(coordinator|evaluator)" <doc>` cross-referenced with `ls scripts/repo_review_*.py`.
- **Model-identifier verification:** `rg "gpt-5\.[0-9]|claude-sonnet-4-[0-9]|claude-opus-4-[0-9]" <doc>` cross-referenced with `tools/langchain_client.py:96-98` (`_default_slots`).
- **Workflow-name verification:** `rg "pr-00-gate|agents-(autofix-dispatcher|keepalive-loop|80-pr-event-hub|81-gate-followups|guard)\.yml" <doc>` cross-referenced with the union of `.github/workflows/` and `templates/consumer-repo/.github/workflows/` (the workflow files live in two places per `CLAUDE.md`).

Internal contradiction was caught by reading each doc end-to-end against itself and against its named authoritative sources; the now-resolved contradiction in `docs/AGENTS_POLICY.md` between "Covered files" (2 named) and the Verification checklist ("three workflows") is one such case.

GitNexus was not required and was not invoked, per the issue's Non-Goals.

## Follow-up issues filed by this audit

- [#2098](https://github.com/stranske/Workflows/issues/2098) — `docs/AGENTS_POLICY.md` contradictory: "Covered files" lists 2 workflows but "Verification checklist" names "three workflows".
- [#2099](https://github.com/stranske/Workflows/issues/2099) — `docs/LABELS.md` stale: missing `agent:claude` / `agent:auto` / `agent:retry` / `agent:rate-limited`; documents unused `agent:codex-invite`. LABELS.md is consumer-synced via `.github/sync-manifest.yml`.
- [#2102](https://github.com/stranske/Workflows/issues/2102) — `docs/ci/WORKFLOWS.md` target-layout diagram still shows Gate flowing directly to `Reusable 18 Autofix` instead of the dispatcher/loop path.

No additional issues were filed for the already-resolved instances (#2085, #2088, #2098) since their PRs are merged on `main`.
