# Agents Guidance — Keepalive Changes

Automation agents touching **any** keepalive code path must consult the following documents before making changes:

## Required Reading

1. **[`GoalsAndPlumbing.md`](GoalsAndPlumbing.md)** — Canonical contract covering:
   - Activation prerequisites (labels, human kickoff, Gate status)
   - Instruction comment formatting and required hidden markers
   - Dispatch, acknowledgement, and branch-sync responsibilities
   - Pause/resume labels and run-cap enforcement
   - The full lifecycle sequence

2. **[`MULTI_AGENT_ROUTING.md`](MULTI_AGENT_ROUTING.md)** — Multi-agent architecture:
   - How `agent:*` labels route to different agent workflows
   - Task appendix injection into prompts
   - Adding support for new agents (Claude, Gemini, etc.)
   - Why explicit task injection matters

3. **[`Observability_Contract.md`](Observability_Contract.md)** — Required observability:
   - Mandatory one-line summaries
   - Marker formats for instruction comments
   - Decision point visibility

4. **[`../analysis/autopilot-40pr-evaluation-feb-2026.md`](../analysis/autopilot-40pr-evaluation-feb-2026.md)** — Auto-pilot pipeline evaluation:
   - 40-PR sample analysis (Workflows + TMP repos)
   - Component-by-component assessment
   - Recommendations and elements to preserve

## Auto-Pilot Integration

The keepalive loop is one stage within the larger **auto-pilot pipeline** (`agents-auto-pilot.yml`). Understanding their relationship is essential:

```
Auto-pilot pipeline:
  format → optimize → apply → capability-check → CREATE-PR → KEEPALIVE → verify → done
                                                      │            │
                                                      │            └─ Event-driven loop:
                                                      │               Gate pass → task appendix
                                                      │               → Codex CLI → push → repeat
                                                      └─ Creates branch + PR with issue context
```

### How Keepalive Fits In

| Auto-pilot does... | Keepalive does... |
|--------------------|--------------------|
| Formats and enriches the issue | Drives the agent through PR tasks |
| Creates the PR and branch | Evaluates Gate results and remaining work |
| Dispatches the next pipeline step | Builds task appendix from PR body checkboxes |
| Triggers verification post-merge | Dispatches Codex CLI with explicit task context |

### Critical Integration Points

1. **PR body is the contract**: Auto-pilot writes structured tasks into the PR body. Keepalive reads these tasks via the task appendix. If the PR body format changes, both must be updated together.

2. **Labels are handoff signals**: Auto-pilot adds `agent:codex` → keepalive loop activates. Keepalive adds `needs-human` after 3 failures → auto-pilot stops dispatching agent iterations.

3. **Gate is the trigger**: Keepalive is event-driven via Gate `workflow_run` completion. Auto-pilot's `monitor-pr` step watches for keepalive progress. Neither polls — both react to events.

4. **Self-dispatch**: Auto-pilot uses `force_step` re-dispatch, not label changes, to sequence its stages. The keepalive loop is triggered independently by Gate completion, not by auto-pilot dispatch.

## Key Principles

1. **Task Focus**: Agents must work on PR tasks, not unrelated improvements. Tasks are explicitly injected via the task appendix.

2. **Agent Agnostic**: The keepalive prompt is agent-agnostic. Routing is determined by the `agent:*` label, not hardcoded agent names.

3. **No `@codex` in Prompts**: Do not use `@codex` or other agent mentions in automated prompts—this can trigger the UI version of agents. Let the routing handle which agent runs.

4. **Verify Before Marking Complete**: Only mark task checkboxes complete after verifying the implementation works.

5. **Follow-up Chain Depth**: The verification pipeline caps follow-up chains at depth 2 (original + 2 follow-ups). After that, `needs-human` is applied instead of creating more follow-up issues.

## Keepalive Implementations

The repository supports two keepalive implementations. The **Codex CLI keepalive** is the current, canonical flow. The **legacy UI connector-bot** flow is retained for historical context and compatibility.

See [`Keepalive_Approaches.md`](Keepalive_Approaches.md) for a full comparison and the rationale for preferring the CLI approach.

Do not mark checklist items complete or dispatch new keepalive rounds until the acceptance criteria in the canonical guide are satisfied. Update all relevant documents together if the contract evolves.
