# Agent Automation & Telemetry Overview

_Last updated: 2026-01-12_

This document captures the trimmed agent automation surface after Issue #2190. The GitHub Actions footprint centers on the
Agents 70 Orchestrator plus the keepalive loop that is driven by Gate `workflow_run` events. Legacy label-forwarding wrappers
remain retired, but the keepalive loop is an active path for PR progression.

## High-Level Flow

```
Manual dispatch / 30-minute schedule ──▶ agents-70-orchestrator.yml
                                        │
                                        ├─ Readiness probes (GraphQL assignability)
                                        ├─ Optional Codex preflight diagnostics
                                        ├─ Optional issue verification (label + assignment parity)
                                        ├─ Watchdog sweep for Codex bootstrap health
                                        └─ Optional keepalive sweep (checklist nudge)

Gate workflow_run (PRs) ───────────────▶ agents-keepalive-loop.yml
                                        │
                                        ├─ Evaluate PR keepalive guardrails
                                        ├─ Run the registry-backed agent via its reusable runner workflow
                                        └─ Loop on subsequent Gate completions
```

- No automatic label forwarding remains. Maintainers trigger the orchestrator directly from the Actions tab (manual
  `workflow_dispatch`) or allow the 30-minute schedule to run readiness + watchdog checks.
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

- **Triggers:** `schedule` (every 30 minutes) and manual `workflow_dispatch` with curated inputs.
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

| Step | What It Does | Execution Pattern | Labels Added |
|------|--------------|-------------------|--------------|
| **Format** | Structures issue into standard template | ✅ Inline: `issue_formatter.py` | `agents:formatted` |
| **Optimize** | Analyzes and suggests improvements | ✅ Inline: `issue_optimizer.py` | (none - adds comment) |
| **Apply** | Applies optimization suggestions | ✅ Inline: `apply_suggestions()` | `agents:apply-suggestions` |
| **Capability Check** | Validates agent can handle task | 🏷️ Label: `agent:<name>` (registry default or runner override) | `agent:<name> (registry default or runner override)` |
| **Create PR** | Creates branch and initial PR | ✅ Direct: GitHub API | (converts issue to PR) |
| **Monitor** | Tracks PR progress via keepalive | 🏷️ Label: `agents:keepalive` (triggers keepalive) | `agents:keepalive` |
| **Check Completion** | Verifies all tasks done, CI passes | ✅ Inline: Checks CI status directly | (checks state) |
| **Trigger Merge** | Queues PR for auto-merge | 🏷️ Label: `automerge` (orchestrator merges) | `automerge` |
| **Verify** | Runs verification after merge | 🏷️ Label: `verify:evaluate` (verifier workflow) | `verify:evaluate` |

**Why the distinction?**
- **Inline** = Simple data transformation that can complete in seconds
- **Label delegation** = Complex operations requiring external systems (CI checks, LLM analysis, scheduled orchestration)

**Label Semantics (as of 2026-02-06):**
- Labels added during inline steps are **status markers** indicating completion
- Labels track workflow state and enable flow control (e.g., `HAS_APPLY` checks for `agents:apply-suggestions`)
- Other workflows that trigger on these labels MUST check for `agents:auto-pilot` and skip if present
- This preserves standalone label-triggered workflows while respecting auto-pilot's inline execution model

### State Tracking

The workflow tracks state by:
- Reading issue/PR labels
- Checking for optimizer output comments
- Monitoring linked PRs
- Counting auto-pilot step comments

### LangSmith Tracing

LangSmith provides observability for all LangChain-based LLM calls in the
workflow system. When enabled, every `client.invoke()` call automatically
generates a trace that records prompt, response, latency, and token usage.

#### Enabling LangSmith

Set the `LANGSMITH_API_KEY` repository secret. On module load
`tools/llm_provider.py` detects the key and configures the environment:

| Variable | Set automatically | Purpose |
|----------|-------------------|---------|
| `LANGCHAIN_TRACING_V2` | `true` | Enables LangChain v2 tracing |
| `LANGCHAIN_PROJECT` | `workflows-agents` (default) | Groups traces by project |
| `LANGCHAIN_API_KEY` | Copied from `LANGSMITH_API_KEY` | LangChain SDK auth |

Override the project by setting `LANGCHAIN_PROJECT` before import.

#### Standardized Metadata

All LLM-calling scripts use `build_langsmith_metadata()` (from
`tools/llm_provider`) to attach consistent metadata to every invocation:

```python
from tools.llm_provider import build_langsmith_metadata

config = build_langsmith_metadata(
    operation="verify_pr",
    pr_number=42,
)
response = client.invoke(prompt, config=config)
```

**Metadata fields** attached to every trace:

| Field | Source | Example |
|-------|--------|---------|
| `repo` | `GITHUB_REPOSITORY` | `stranske/Workflows` |
| `run_id` | `GITHUB_RUN_ID` | `12345678` |
| `issue_or_pr_number` | Arg or `PR_NUMBER`/`ISSUE_NUMBER` env | `42` |
| `operation` | Caller-supplied | `verify_pr` |
| `langsmith_project` | `LANGCHAIN_PROJECT` (when enabled) | `workflows-agents` |

**Tags** for filtering in the LangSmith UI:

- `workflows-agents`
- `operation:<name>`
- `repo:<owner/repo>`
- `issue_or_pr:<number>`
- `run_id:<id>`

#### Trace IDs in Metrics

The autopilot metrics collector accepts trace IDs via CLI or environment:

```bash
python scripts/autopilot_metrics_collector.py \
  --metric-type step \
  --langsmith-trace-id "$TRACE_ID" \
  ...
```

Or set `LANGSMITH_TRACE_ID` / `LANGSMITH_TRACE_URL` in the environment.
When only a trace ID is provided, the URL is auto-derived as
`https://smith.langchain.com/r/<trace_id>`.

Metrics records may include:

- `langsmith_trace_id` — the LangSmith trace identifier.
- `langsmith_trace_url` — a direct, clickable link to the trace in the
  LangSmith UI.

These fields are optional and are omitted when LangSmith is unavailable.

#### Graceful Degradation

When `LANGSMITH_API_KEY` is **not** set:

- `LANGSMITH_ENABLED` is `False`
- No tracing environment variables are modified
- `build_langsmith_metadata()` still returns a valid config dict (without
  the `langsmith_project` field)
- All LLM calls proceed normally — tracing is purely additive

#### Scripts Using Standardized Metadata

| Script | Operations |
|--------|------------|
| `scripts/langchain/pr_verifier.py` | `evaluate`, `compare` |
| `scripts/langchain/followup_issue_generator.py` | `analyze_verification`, `generate_tasks`, `generate_acceptance_criteria`, `format_followup_issue` |

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
4. Repeat manual dispatches as needed; scheduled runs provide 30-minute coverage for stale bootstrap detection.

## Alerting Threshold Tuning

Metrics alerting thresholds live in `config/alerting-thresholds.json` and should be tuned with both baseline behavior and
alert fatigue in mind.

- Start from a recent 30 to 60 day baseline for success rate, duration, and token usage. Use medians or p95s rather than
  single-day outliers.
- Prefer incremental adjustments (5 to 10 percent) instead of large jumps so you can attribute changes to real shifts.
- Separate short-lived spikes from sustained drift. For example, only lower success rate thresholds after several runs show
  the same regression.
- Revisit thresholds after major workflow or model changes. Each new model or large prompt update can shift token usage and
  duration distributions.
- Keep alert volume manageable: if the same threshold fires repeatedly without action, relax it or add a higher-severity
  tier so only actionable alerts page maintainers.

## Metrics Retention

Metrics logs are append-only NDJSON files (for example `metrics-history.ndjson` and `keepalive-metrics.ndjson`). Retention
policy is defined in `config/retention-policy.json`, with daily, weekly, and monthly windows to keep recent data hot while
archiving older entries under `archives/metrics/`.

Run retention manually:
- `python scripts/metrics_retention.py` (uses defaults + `agent-metrics/` discovery)
- `python scripts/metrics_retention.py --dry-run` to preview without writing

Archived data can be restored when needed:
- `python scripts/metrics_retention.py --restore --archive-path archives/metrics/metrics-history/weekly --output-path metrics-history.ndjson`

Retention operations are tracked in `metrics-retention.ndjson`, including record counts, archive destinations, and storage
reduction percentages.

`.github/workflows/maint-metrics-retention.yml` is manual and pull-request validation only; its no-op nightly cron was
removed because it restored no metrics artifacts before running. Use `workflow_dispatch` (with the optional `dry_run`
input) for real retention runs. Pull-request triggers run in `--dry-run` mode when the script, policy config, or workflow
file changes. The retention log is uploaded as the `metrics-retention-log` artifact and the storage reduction percentage
is surfaced in the workflow step summary. Fresh checkouts with no metrics logs are treated as successful no-op runs:
the script writes a zero-file `retention_summary` record so pull-request validation still produces durable evidence.

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

**Current Solution (Complete Fix as of 2026-01-12):** All preparation steps now run **inline** within the auto-pilot workflow:

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

### Auto-Pilot Stuck in Infinite Loop (Issue #1212)

**Symptom:** Auto-pilot workflow repeatedly dispatches itself, making 30+ attempts over several hours without progressing past apply step. Label `agents:apply-suggestions` is added and removed in a loop.

**Root Cause (Fixed 2026-02-06):** GitHub App token behavior change exposed a missing protection in the optimizer workflow:

**Timeline:**
1. **Jan 12 (c9f639d):** Auto-pilot redesigned for inline execution - labels became "status markers, not triggers"
2. **Feb 2 (0d6103d):** GitHub App tokens added to ALL workflows for rate limit management
3. **Feb 6 (issue #1212):** Loop detected - optimizer was removing labels that auto-pilot needed for state tracking

**The Loop Mechanics:**
```
1. Auto-pilot apply step completes → adds agents:apply-suggestions label
2. Optimizer workflow TRIGGERS (enabled by App token, not GITHUB_TOKEN)
3. Optimizer had NO protection for auto-pilot → runs and removes the label  
4. Auto-pilot checks HAS_APPLY → false (label gone!)
5. Auto-pilot logic: "No label? Must need to run apply again"
6. Back to step 1 → INFINITE LOOP
```

**Why This Wasn't Caught Earlier:**
- `GITHUB_TOKEN` has built-in anti-recursion: workflows it triggers don't trigger other workflows
- **GitHub App tokens DO trigger other workflows** - no anti-recursion protection
- The optimizer violation of "labels as status markers only" was masked until App tokens were added

**Current Solution (Fixed 2026-02-06):**

Added protection checks in `agents-issue-optimizer.yml` (lines 57-97):
```yaml
elif [[ "$LABEL_NAME" == "agents:apply-suggestions" ]]; then
  # Skip if auto-pilot label is present (auto-pilot manages this label for state)
  if gh issue view "${{ github.event.issue.number }}" --json labels \
      --jq '.labels[].name' | grep -qx 'agents:auto-pilot'; then
    echo "should_run=false" >> "$GITHUB_OUTPUT"
    echo "Skipping: auto-pilot label present (manages apply inline)"
  else
    # ... run normally for standalone use
  fi
```

Same protection added for `agents:format` and `agents:optimize` labels.

**Architecture Clarification:**

Labels in auto-pilot are **hybrid: status markers with functional side effects**:
- ✅ **Status markers:** Indicate completion (e.g., "apply step finished")
- ✅ **Functional checks:** Read back for flow control (e.g., `HAS_APPLY` at line 523)
- ❌ **NOT triggers:** Should not trigger other workflows when auto-pilot is active

**Label Semantics:**
- `agents:formatted` - Format step completed
- `agents:apply-suggestions` - Apply step completed (suggestions have been applied)
- `agent:codex` - Agent capability check completed
- `agents:auto-pilot` - Auto-pilot orchestration is active
- `runner:<agent>` - Optional auto-pilot override (`runner:claude`, `runner:codex`, etc.) that selects the agent without triggering the issue intake workflow

**Prevention:**
- Workflows triggered by auto-pilot status labels MUST check for `agents:auto-pilot` presence
- If auto-pilot is present, skip execution (auto-pilot runs logic inline)
- This respects the inline execution model while preserving standalone label-triggered workflows

### Keepalive Not Triggering

**Symptom:** Codex PR has tasks but keepalive doesn't post continuation commands.

**Root Cause:** Covered in [`docs/keepalive/KEEPALIVE_TROUBLESHOOTING.md`](keepalive/KEEPALIVE_TROUBLESHOOTING.md).

## Future Enhancements

- Extend `params_json` to cover any additional toggles without growing the dispatch form (embed an `options_json` string when nested structures are required).
- Consider adding a lightweight CLI wrapper that posts curated `params_json` payloads for common scenarios.
- Monitor usage; if the 30-minute schedule proves redundant, convert it to manual-only to further reduce background noise.

For questions or updates, open an issue labeled `agent:codex` describing the desired change.
