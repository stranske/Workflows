# Agent Automation & Telemetry Overview

_Last updated: 2026-10-12_

This document captures the trimmed agent automation surface that remains after Issue #2190. The GitHub Actions footprint now
consists of a single orchestrator workflow plus the reusable composite it consumes. Everything else that previously handled
label forwarding, watchdog wrappers, or Codex bootstrap fallbacks has been removed.

## High-Level Flow

```
Manual dispatch / 20-minute schedule ──▶ agents-70-orchestrator.yml
                                        │
                                        ├─ Readiness probes (GraphQL assignability)
                                        ├─ Optional Codex preflight diagnostics
                                        ├─ Optional issue verification (label + assignment parity)
                                        ├─ Watchdog sweep for Codex bootstrap health
                                        └─ Codex keepalive sweep (checklist nudge)
```

- No automatic label forwarding remains. Maintainers trigger the orchestrator directly from the Actions tab (manual
  `workflow_dispatch`) or allow the 20-minute schedule to run readiness + watchdog checks.
- Codex keepalive now runs as part of the orchestrator invocation. Configure thresholds or disable it entirely via the
  `params_json` payload (e.g. `{ "enable_keepalive": false }`).
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

## Future Enhancements

- Extend `params_json` to cover any additional toggles without growing the dispatch form (embed an `options_json` string when nested structures are required).
- Consider adding a lightweight CLI wrapper that posts curated `params_json` payloads for common scenarios.
- Monitor usage; if the 20-minute schedule proves redundant, convert it to manual-only to further reduce background noise.

For questions or updates, open an issue labeled `agent:codex` describing the desired change.
