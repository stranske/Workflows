# Agent Automation & Telemetry Overview

_Last updated: 2026-11-25_

This document captures the trimmed agent automation surface after Issue #2190
and the retirement of the Agents 70 orchestrator stack
(`agents-70-orchestrator.yml`, `reusable-70-orchestrator-init.yml`,
`reusable-70-orchestrator-main.yml`, `reusable-16-agents.yml`). The GitHub
Actions footprint centers on **Agents Keepalive Loop** and the
**Codex belt** (`agents-71/72/73`), and **Agents 64** verification. Legacy
label-forwarding wrappers remain retired.

## High-Level Flow

```
Gate workflow_run (PRs) ───────────────▶ agents-keepalive-loop.yml
                                        │
                                        ├─ Evaluate PR keepalive guardrails
                                        ├─ Run the registry-backed agent via its reusable runner workflow
                                        └─ Loop on subsequent Gate completions

agents-keepalive-sweep.yml (hourly) ───▶ agents-keepalive-loop.yml
                                        (stalled PR resync for eligible labels)

eligible issue ───────────────────────▶ shared opener
                                        (inline format → optimize → apply → PR → keepalive → verify)

Codex belt (71 → 72 → 73) ─────────────▶ issue queue → worker PR → conveyor merge
```

- **Keepalive** on PRs is driven by Gate `workflow_run` events
  (`agents-keepalive-loop.yml`), with hourly resync via `agents-keepalive-sweep.yml`.
  PR-meta on Workflows submits keepalive worker commands directly ([#5162](https://github.com/stranske/Workflows/pull/5162));
  measured dispatch capacity is enforced ([#5163](https://github.com/stranske/Workflows/pull/5163)).
- Review the [keepalive contract](keepalive/GoalsAndPlumbing.md) before changing keepalive workflows. For branch recovery, follow the [recovery procedure](keepalive/Observability_Contract.md#8-orchestrator-contract) and verify the new head with the [branch-sync gate](keepalive/GoalsAndPlumbing.md#9-branch-sync-gate).
- Bootstrap PR creation, diagnostics, and stale issue escalation now live in the
  belt, Auto-Pilot, and keepalive surfaces. Historical wrappers
  (`agents-41-assign*.yml`, `agents-42-watchdog.yml`, and the Agents 70 stack) were
  deleted.

## Key Workflows

### `agents-64-verify-agent-assignment.yml`

- **Triggers:** `workflow_call` and `workflow_dispatch`.
- **Behaviour:** Fetches the issue, ensures the `agent:codex` (or configured) label
  is present, validates that one of the configured valid assignees is assigned, and
  publishes a step summary table documenting the outcome.
- **Usage:** Ad-hoc verification from the Actions tab or callable reuse from intake
  and bridge workflows.

The default valid assignee roster includes `copilot`, `chatgpt-codex-connector`, and
`stranske-automation-bot`; provide a comma-separated override when onboarding
additional automation accounts or running spot checks against bespoke actors.

### Agent PR promotion

The [shared closer](ops/LOCAL_LANES.md#lanes-overview) checks the current PR head, required checks and review clearance before merging.

## Related Automation

While the agent wrappers were removed, maintenance automation still supports the broader workflow stack:

- The Gate summary job writes consolidated run summaries, applies low-risk fixes, uploads patches when automation cannot push directly after `pr-00-gate.yml` finishes, and now owns the CI failure tracker end to end.

## Historical Auto-Pilot Workflow Architecture

The [shared opener and closer](ops/LOCAL_LANES.md#lanes-overview) own current issue admission and guarded promotion. The original Auto-Pilot steps below document the retired workflow.

The `agents-auto-pilot.yml` workflow implements a complete end-to-end automation pipeline from issue creation to PR merge.

### Execution Model

**Inline execution for issue preparation** (format, optimize, apply):
- These steps run as inline Python scripts within the auto-pilot workflow
- No child workflow triggering
- Results are immediately available for next step

**Label delegation for infrastructure operations** (merge, verify):
- These steps add labels to hand off to specialized infrastructure
- `automerge` → guarded merge lanes
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
| **Trigger Merge** | Queues PR for auto-merge | 🏷️ Label: `automerge` | `automerge` |
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

1. Apply `agents:auto-pilot` to an issue formatted with the Agent task template.
2. Optional: add `runner:<name>` to override the registry default agent.
3. Monitor the Auto-Pilot run summary and linked PR in Actions.
4. For manual issue assignment checks, dispatch **Agents 64 Verify Agent Assignment**
   with `issue_number`.

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
- `python scripts/metrics_retention.py --dry-run` to preview. It writes the audit log and leaves metrics files and archives unchanged.

Archived data can be restored when needed:
- `python scripts/metrics_retention.py --restore --archive-path archives/metrics/metrics-history/weekly --output-path metrics-history.ndjson`

Retention operations are tracked in `metrics-retention.ndjson`, including record counts, archive destinations, and storage
reduction percentages.

[Maint Metrics Retention](../.github/workflows/maint-metrics-retention.yml) accepts `workflow_dispatch` with an optional
`dry_run` input (default `false`). Pull requests run in `--dry-run` mode when the script, policy config, or workflow
changes. The job uses the selected ref's checkout and does not fetch existing metrics artifacts. A checkout without
metrics logs succeeds with a zero-file `retention_summary`. The job reports storage reduction in the step summary
and retains the `metrics-retention-log` audit artifact for 90 days. Run the CLI where your metrics files live to preserve
`archives/metrics/` for restoration. The hosted artifact contains the audit log only.

## Security Considerations

- All sensitive operations continue to rely on `SERVICE_BOT_PAT` when available. The workflows gracefully fall back to
  `GITHUB_TOKEN` only when explicitly allowed by the repository variables.
- Inputs that toggle optional behaviour remain string-valued (`'true'` / `'false'`) to stay compatible with callable
  workflows.

## Troubleshooting

### Historical Auto-Pilot Stuck or Not Progressing

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
- Avoid workflow_run chains — they introduce complexity, latency, and failure points

**Manual Recovery (if using old version):**
- Remove `agents:auto-pilot` label
- Manually run the needed phase by adding appropriate label
- Once complete, re-add `agents:auto-pilot` to continue

### Historical Auto-Pilot Stuck in Infinite Loop (Issue #1212)

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

**Current ownership check.** The [issue optimizer](../.github/workflows/agents-issue-optimizer.yml) reads the issue’s current labels in the event repository before checkout. On a label-triggered Analyze or Apply, an issue carrying `agents:auto-pilot` stays with Auto-Pilot. A failed label read stops the standalone job before it can run either phase. An explicit operator dispatch keeps its selected phase.

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

- Extend Auto-Pilot `params_json` / inline toggles without growing dispatch forms.
- Use the [shared closer](ops/LOCAL_LANES.md#lanes-overview) result to inspect PR promotion eligibility.

For questions or updates, open an issue labeled `agent:codex` describing the desired change.