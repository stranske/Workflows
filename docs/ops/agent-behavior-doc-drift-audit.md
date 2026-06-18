# Agent Behavior Doc Drift Audit

Issue: [#2450](https://github.com/stranske/Workflows/issues/2450)

This audit covers active operator-facing docs and workflow comments that describe
agent behavior, verifier follow-up creation, and registry-backed routing. It
excludes historical plans, archived docs, and analysis reports unless they are
linked as current operator guidance.

## Source Of Truth

| Behavior | Source |
| --- | --- |
| Automatic verifier follow-up issue creation is disabled | `.github/workflows/reusable-agents-verifier.yml` follow-up step is guarded with `if: ${{ github.run_id == 0 }}` and comments direct operators to `verify:create-issue` |
| Issue-only verifier follow-up creation is label-triggered | `.github/workflows/agents-verify-to-issue-v2.yml` runs on `pull_request_target` labeled `verify:create-issue` |
| Follow-up issue plus PR creation is label-triggered | `.github/workflows/agents-verify-to-new-pr.yml` runs on `pull_request_target` labeled `verify:create-new-pr` |
| Registry-backed routing is active | `.github/agents/registry.yml` plus `docs/keepalive/MULTI_AGENT_ROUTING.md` |

## Reviewed Hits

| Path | Claim | Implementation reference | Disposition | Fix / follow-up |
| --- | --- | --- | --- | --- |
| `README.md` | Pipeline table said CONCERNS/FAIL creates a follow-up issue. | Automatic verifier issue creation is disabled in `reusable-agents-verifier.yml`; label-triggered workflows own creation. | `confirmed-stale` | Updated table to say maintainers or automation apply `verify:create-issue` / `verify:create-new-pr`. |
| `README.md` | Verification paragraph already said maintainers or automation can apply `verify:create-new-pr`. | `agents-verify-to-new-pr.yml` label trigger. | `already-correct` | No change. |
| `docs/WORKFLOW_GUIDE.md` | `agents-verify-to-issue-v2.yml` and `agents-verify-to-new-pr.yml` sections describe label-triggered follow-up workflows. | Both workflows gate on the matching label. | `already-correct` | No change. |
| `docs/WORKFLOW_GUIDE.md` | Verifier outputs said a follow-up issue is opened when the verdict is FAIL. | Automatic verifier issue creation is disabled in `reusable-agents-verifier.yml`; labels trigger follow-up work. | `confirmed-stale` | Reworded to the manual label-triggered path. |
| `docs/WORKFLOW_GUIDE.md` | Troubleshooting said failures open issues when the verifier is enabled and has permissions. | Follow-up creation requires `verify:create-issue` or `verify:create-new-pr`. | `confirmed-stale` | Reworded missing-follow-up guidance to check labels. |
| `docs/ci/WORKFLOWS.md` | Verifier docs said reusable verifier and issue-only follow-up workflows create issues automatically, and implied both follow-up labels share the chain-depth cap. | Automatic verifier issue creation is disabled; `verify:create-issue` is label-triggered issue-only creation; `verify:create-new-pr` is the label-triggered path with chain-depth enforcement. | `confirmed-stale` | Reworded verifier and follow-up workflow rows; narrowed chain-depth wording to `verify:create-new-pr`. |
| `docs/ci/WORKFLOW_SYSTEM.md` | Workflow inventory describes verify-to-issue and verify-to-new-pr as label-triggered. | Workflow `on: pull_request_target` labeled conditions. | `already-correct` | No change. |
| `docs/LABELS.md` | Label inventory says `verify:create-issue` / `verify:create-new-pr` create follow-up work when applied to a merged PR with verifier report. | Label-triggered workflows. | `already-correct` | No change. |
| `.github/workflows/reusable-agents-verifier.yml` | Workflow comments explicitly say automatic follow-up issue creation is disabled. | Same workflow step is unreachable under normal run IDs. | `already-correct` | No change. |
| `.github/workflows/agents-verify-to-issue-v2.yml` | Workflow comment says adding `verify:create-issue` to a merged PR creates a follow-up issue. | Job-level label guard and merged-PR check. | `already-correct` | No change. |
| `.github/workflows/agents-verify-to-new-pr.yml` | Workflow comment says adding `verify:create-new-pr` to a merged PR creates a follow-up issue and triggers auto-pilot. | Job-level label guard, issue creation, and auto-pilot dispatch steps. | `already-correct` | No change. |
| `docs/keepalive/Agents.md` | Routing docs describe registry-backed `agent:<name>` labels and runner overrides. | `.github/agents/registry.yml` and existing docs contract test. | `already-correct` | No change. |
| `docs/keepalive/MULTI_AGENT_ROUTING.md` | Routing table covers enabled registry agents. | Existing `test_agent_routing_doc_covers_enabled_registry_agents`. | `already-correct` | No change. |

## Regression Guard

Added `tests/docs/test_workflow_source_docs.py::test_active_docs_do_not_claim_automatic_verifier_followup`.
The test scans active verifier docs and fails if they imply CONCERNS/FAIL
automatically opens a follow-up issue without nearby manual-label wording for
`verify:create-issue` or `verify:create-new-pr`.

## Follow-Up Issues

No larger nonlocal remediation was found. The confirmed stale active-doc claims
were direct wording corrections in this PR.
