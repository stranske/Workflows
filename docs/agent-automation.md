# Agent Automation & Telemetry Overview

_Last updated: 2026-01-12_

This document captures the trimmed agent automation surface after Issue #2190. The GitHub Actions footprint centers on the
Agents 70 Orchestrator plus the keepalive loop that is driven by Gate `workflow_run` events. Legacy label-forwarding wrappers
remain retired, but the keepalive loop is an active path for PR progression.

## High-Level Flow

```
Manual dispatch / 20-minute schedule ──▶ agents-70-orchestrator.yml
                                        │
                                        ├─ Readiness probes (GraphQL assignability)
                                        ├─ Optional Codex preflight diagnostics
                                        ├─ Optional issue verification (label + assignment parity)
                                        ├─ Watchdog sweep for Codex bootstrap health
                                        └─ Optional keepalive sweep (checklist nudge)

Gate workflow_run (PRs) ───────────────▶ agents-keepalive-loop.yml
                                        │
                                        ├─ Evaluate PR keepalive guardrails
                                        ├─ Run Codex CLI via reusable-codex-run.yml
                                        └─ Loop on subsequent Gate completions
```

- No automatic label forwarding remains. Maintainers trigger the orchestrator directly from the Actions tab (manual
  `workflow_dispatch`) or allow the 20-minute schedule to run readiness + watchdog checks.
- Codex keepalive on PRs is driven by the Gate `workflow_run` loop. The orchestrator sweep is optional and can be
  disabled via `params_json` (e.g. `{ "enable_keepalive": false }`).
- Keepalive contract guidance lives in [`docs/keepalive/GoalsAndPlumbing.md`](keepalive/GoalsAndPlumbing.md); review it before
  adjusting any keepalive workflows or recovery logic. Follow the recovery playbook in
  [`docs/keepalive/SyncChecklist.md`](keepalive/SyncChecklist.md) when branch-sync intervention is required.
- Bootstrap PR creation, diagnostics, and stale issue escalation now live entirely inside `agents-70-orchestrator.yml` and the
  `reusable-16-agents.yml` composite it calls. Historical wrappers (`agents-41-assign*.yml`, `agents-42-watchdog.yml`, etc.) were
  deleted.

## Key Workflow

### `agents-70-orchestrator.yml`

- **Triggers:** `schedule` (every 20 minutes) and manual `workflow_dispatch` with curated inputs.
- **Inputs:** `enable_readiness`, `readiness_agents`, `enable_preflight`, `codex_user`,
  `enable_verify_issue`, `verify_issue_number`, `verify_issue_valid_assignees`, `enable_watchdog`, `draft_pr`, plus an extensible
  `params_json` string for long tail toggles (currently `diagnostic_mode`, `readiness_custom_logins`, `codex_command_phrase`,
  `require_all`, `enable_keepalive`, `keepalive_idle_minutes`, `keepalive_repeat_minutes`, `keepalive_labels`,
  `keepalive_command`).
- **Behaviour:** delegates directly to `reusable-16-agents.yml`, which orchestrates readiness probes, Codex bootstrap, issue
  verification, and watchdog sweeps. The JSON options map is parsed via `fromJson()` so new flags can be layered without
  exploding the dispatch form beyond GitHub's 10-input limit.
- **Permissions:** retains `contents`, `pull-requests`, and `issues` write scopes to continue authoring Codex PRs or posting
  remediation comments.
- **Outputs:** inherits the reusable workflow's job summaries, watchdog tables, and readiness reports.

### Reusable Composite

`reusable-16-agents.yml` remains the single source of truth for agent automation logic:

- exposes a `workflow_call` interface so the orchestrator can exercise readiness, preflight, verification, and watchdog routines.
- keeps compatibility inputs such as `readiness_custom_logins`, `require_all`, `enable_preflight`, `enable_verify_issue`,
  `enable_watchdog`, `draft_pr`, and the pass-through `options_json` (embedded via `params_json`) for additional toggles.
- emits a Codex keepalive sweep that looks for stalled checklists on `agent:codex` PRs and republishes the
  `@codex plan-and-execute` command when the agent has been idle longer than the configured threshold (defaults: 10 minute
  idle threshold, 30 minute cooldown between nudges).
- writes summarized Markdown + JSON artifacts for readiness probes and watchdog runs.

### Verify Agent Assignment Workflow

`agents-64-verify-agent-assignment.yml` exposes the issue verification logic as a standalone reusable workflow with a parallel
`workflow_dispatch` entry point. Supply an `issue_number` and the workflow fetches the issue, ensures the `agent:codex`
label is present, validates that one of the configured valid assignees is assigned, and publishes a step summary table
documenting the outcome. `reusable-16-agents.yml` now delegates its issue verification job to this workflow so the same checks
are available for ad-hoc dispatches from the Actions tab.

The default valid assignee roster includes `copilot`, `chatgpt-codex-connector`, and `stranske-automation-bot`; provide a comma-separated override when onboarding additional automation accounts or running spot checks against bespoke actors.

## Related Automation

While the agent wrappers were removed, maintenance automation still supports the broader workflow stack:

- The Gate summary job writes consolidated run summaries, applies low-risk fixes, uploads patches when automation cannot push directly after `pr-00-gate.yml` finishes, and now owns the CI failure tracker end to end.

## Auto-Pilot Workflow Architecture

The `agents-auto-pilot.yml` workflow implements a complete end-to-end automation pipeline from issue creation to PR merge.

### Execution Model

**Inline execution for issue preparation** (format, optimize, apply):
- These steps run as inline Python scripts within the auto-pilot workflow
- No child workflow triggering
- Results are immediately available for next step

**Label delegation for infrastructure operations** (merge, verify):
- These steps add labels to hand off to specialized infrastructure
- `automerge` → Orchestrator's scheduled merge job
- `verify:evaluate` → Dedicated verifier workflow
- These are asynchronous by design and shared across all workflows

### Key Steps

| Step | What It Does | Execution Pattern |
|------|--------------|-------------------|
| **Format** | Structures issue into standard template | ✅ Inline: `issue_formatter.py` |
| **Optimize** | Analyzes and suggests improvements | ✅ Inline: `issue_optimizer.py` |
| **Apply** | Applies optimization suggestions | ✅ Inline: `apply_suggestions()` |
| **Capability Check** | Validates agent can handle task | 🏷️ Label: `agent:codex` (triggers capability workflow) |
| **Create PR** | Creates branch and initial PR | ✅ Direct: GitHub API |
| **Monitor** | Tracks PR progress via keepalive | 🏷️ Label: `agents:keepalive` (triggers keepalive) |
| **Check Completion** | Verifies all tasks done, CI passes | ✅ Inline: Checks CI status directly |
| **Trigger Merge** | Queues PR for auto-merge | 🏷️ Label: `automerge` (orchestrator merges) |
| **Verify** | Runs verification after merge | 🏷️ Label: `verify:evaluate` (verifier workflow) |

**Why the distinction?**
- **Inline** = Simple data transformation that can complete in seconds
- **Label delegation** = Complex operations requiring external systems (CI checks, LLM analysis, scheduled orchestration)

### State Tracking

The workflow tracks state by:
- Reading issue/PR labels
- Checking for optimizer output comments
- Monitoring linked PRs
- Counting auto-pilot step comments

### LangSmith Tracing

When LangSmith tracing is enabled for auto-pilot runs, the metrics records may include:

- `langsmith_trace_id` for the LangSmith trace identifier.
- `langsmith_trace_url` with a direct, clickable link to the trace in the LangSmith UI.

These fields are optional and should be omitted when LangSmith is unavailable.

### Re-dispatch Pattern

After each major step, the workflow re-dispatches itself to continue the pipeline. This allows:
- Fresh workflow state for each phase
- Better logging and debugging per step
- Recovery from transient failures

### Usage

1. Use the **Agents 70 Orchestrator** workflow to run readiness checks, Codex bootstrap diagnostics, keepalive sweeps, or
  watchdog checks on demand.
2. Supply additional toggles via `params_json`, for example:
   ```json
   {
     "readiness_custom_logins": "my-bot,backup-bot",
     "diagnostic_mode": "full",
     "codex_command_phrase": "@codex start",
     "enable_bootstrap": true,
     "bootstrap_issues_label": "agent:codex",
     "keepalive_idle_minutes": 10,
     "keepalive_repeat_minutes": 30
   }
   ```
3. Review the run summary for readiness tables, watchdog escalation indicators, and Codex bootstrap status.
4. Repeat manual dispatches as needed; scheduled runs provide 20-minute coverage for stale bootstrap detection.

## Security Considerations

- All sensitive operations continue to rely on `SERVICE_BOT_PAT` when available. The workflows gracefully fall back to
  `GITHUB_TOKEN` only when explicitly allowed by the repository variables.
- Inputs that toggle optional behaviour remain string-valued (`'true'` / `'false'`) to stay compatible with the reusable
  composite.

## Troubleshooting

### Auto-Pilot Stuck or Not Progressing

**Symptom:** The auto-pilot workflow appears to stop after triggering format/optimize/apply steps and doesn't proceed.

**Root Cause (Fixed 2026-01-12):** The original implementation incorrectly used label-based triggering for child workflows within auto-pilot:
1. Auto-pilot added labels like `agents:format`, `agents:optimize`, `agents:apply-suggestions`
2. These triggered separate workflows (`agents-issue-optimizer.yml`)
3. Auto-pilot waited for those workflows to complete via `workflow_run` events
4. **Problem:** workflow_run continuation was unreliable and created race conditions

**Current Solution (Complete Fix):** All preparation steps now run **inline** within the auto-pilot workflow:

| Step | Old Approach | New Approach |
|------|-------------|--------------|
| **Format** | Added `agents:format` label → triggered separate workflow | Runs `issue_formatter.py` inline |
| **Optimize** | Added `agents:optimize` label → triggered separate workflow | Runs `issue_optimizer.py` inline |
| **Apply** | Added `agents:apply-suggestions` label → triggered separate workflow | Runs `apply_suggestions()` inline |

**Benefits:**
- ✅ No workflow_run dependencies or race conditions
- ✅ Single workflow run for entire pipeline (easier debugging)
- ✅ Faster execution (no workflow dispatch overhead)
- ✅ Atomic operations within one job

**Architecture Principle:**
- **Standalone use**: Labels still work independently to trigger `agents-issue-optimizer.yml` for manual use
- **Auto-pilot mode**: All logic executes inline; labels are only added as status markers (e.g., `agents:formatted`)

**Prevention:**
- Child workflows should only be triggered by labels for standalone/manual operations
- Within orchestration workflows like auto-pilot, execute all logic inline as workflow steps
- Avoid workflow_run chains - they introduce complexity, latency, and failure points

**Manual Recovery (if using old version):**
- Remove `agents:auto-pilot` label
- Manually run the needed phase by adding appropriate label
- Once complete, re-add `agents:auto-pilot` to continue

### Keepalive Not Triggering

**Symptom:** Codex PR has tasks but keepalive doesn't post continuation commands.

**Root Cause:** Covered in [`docs/keepalive/KEEPALIVE_TROUBLESHOOTING.md`](keepalive/KEEPALIVE_TROUBLESHOOTING.md).

## Future Enhancements

- Extend `params_json` to cover any additional toggles without growing the dispatch form (embed an `options_json` string when nested structures are required).
- Consider adding a lightweight CLI wrapper that posts curated `params_json` payloads for common scenarios.
- Monitor usage; if the 20-minute schedule proves redundant, convert it to manual-only to further reduce background noise.

For questions or updates, open an issue labeled `agent:codex` describing the desired change.
