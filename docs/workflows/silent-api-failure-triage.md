# Silent API Failure Triage

Issue #3017 audits actions/github-script steps that catch a github.rest error without calling core.setFailed. This is a shape inventory, not a claim that every caught error is a defect. A step is allowed to continue only when it carries the matching inline # best-effort: rationale; mutations required for correctness must aggregate errors and fail the job.

The current inventory contains **45** warning-only steps, including both `github.rest.*` and `github.request` calls. maint-69-sync-labels.yml is the reference hard-failure implementation. The contract test at tests/workflows/test_no_silent_api_failures.py re-scans every workflow, so a new unannotated shape cannot be introduced silently.

| Workflow | Job | Step | Classification | Rationale |
| --- | --- | --- | --- | --- |
| .github/workflows/agents-63-issue-intake.yml | chatgpt_sync | Sync issues | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/agents-73-codex-belt-conveyor.yml | promote | Delete branch after merge | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/agents-73-codex-belt-conveyor.yml | promote | Close source issue | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/agents-73-codex-belt-conveyor.yml | promote | Leave merge confirmation on PR | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/agents-73-codex-belt-conveyor.yml | promote | Re-dispatch dispatcher | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/agents-auto-pilot.yml | auto-pilot | Check step count | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/agents-autofix-loop.yml | needs-human | Add needs-human label and comment | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/agents-autofix-loop.yml | metrics | Collect metrics | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/agents-bot-comment-handler.yml | cleanup | Remove trigger label | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/agents-decompose.yml | decompose | Remove trigger label | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/agents-keepalive-sweep.yml | sweep | Dispatch keepalive loop for open agent PRs | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/agents-moderate-connector.yml | moderate | Evaluate comment for moderation | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/agents-verify-to-issue-v2.yml | create-issue | Remove trigger label | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/autofix.yml | resolve | Resolve PR context | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/health-40-repo-selfcheck.yml | repo-health | Collect repository signals | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/health-40-repo-selfcheck.yml | repo-health | Update failure tracker issue | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/health-40-repo-selfcheck.yml | repo-health | Update repo health snapshot issue | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/health-41-repo-health.yml | rate-limit-check | Check API quota | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/health-41-repo-health.yml | weekly-sweep | Summarise repository health signals | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/maint-46-post-ci.yml | summary | Check Gate summary completion | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/maint-62-integration-consumer.yml | report | Open or update failure issue | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/maint-72-fix-pr-body-conflicts.yml | fix-repos | Check and fix pr_body.md | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/maint-coverage-guard.yml | rate-limit-check | Check API quota | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/pr-00-gate.yml | summary | Report Gate commit status | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/pr-00-gate.yml | summary | Dispatch autofix notification | # best-effort: | The Gate failure remains authoritative and keepalive can retry the advisory dispatch. |
| .github/workflows/reusable-10-ci-python.yml | logs_summary | Summarize workflow jobs | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/reusable-16-agents.yml | preflight | Run agent preflight probes | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/reusable-18-autofix.yml | autofix | Ensure autofix label present | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/reusable-18-autofix.yml | autofix | Label PR (autofix patch available) | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/reusable-18-autofix.yml | autofix | Manage autofix outcome labels | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/reusable-18-autofix.yml | autofix | Upsert consolidated PR comment | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/reusable-18-autofix.yml | autofix | Regression detector (same-repo) | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/reusable-70-orchestrator-main.yml | resolve-orchestrator-context | Resolve PR number and agent alias | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/reusable-70-orchestrator-main.yml | keepalive-prep | Capture keepalive head snapshot | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/reusable-70-orchestrator-main.yml | keepalive-instruction | Emit fallback dispatch | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/reusable-70-orchestrator-main.yml | belt-dispatch-summary | Record keepalive worker outcome | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/reusable-agents-pr-health.yml | scan | Categorise PRs | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/reusable-agents-pr-health.yml | resolve-conflicts | Resolve each conflict | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/reusable-agents-pr-health.yml | fix-checks | Fix each failing PR | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/reusable-agents-verifier.yml | verifier | Resolve agent key from PR labels | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/reusable-agents-verifier.yml | verifier | Open follow-up issue on verifier failure | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/reusable-backplane-conformance.yml | conformance | Comment on PR | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/reusable-bot-comment-handler.yml | dispatch | Assign agent and post context comment | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/reusable-codex-run.yml | codex | Add needs-attention label on non-transient failure | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |
| .github/workflows/selftest-reusable-ci.yml | summarize | Verify matrix artifacts | # best-effort: | Ancillary API failure is logged; reconciliation or the primary workflow result remains authoritative. |

## Maintenance rule

Do not copy these markers to a new mutation by default. If a failed API call would make the workflow falsely report completed work, collect affected targets and call core.setFailed after writing any useful summary, following maint-69-sync-labels.yml.
