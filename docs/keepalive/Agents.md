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

## Key Principles

1. **Task Focus**: Agents must work on PR tasks, not unrelated improvements. Tasks are explicitly injected via the task appendix.

2. **Agent Agnostic**: The keepalive prompt is agent-agnostic. Routing is determined by the `agent:*` label, not hardcoded agent names.

3. **No `@codex` in Prompts**: Do not use `@codex` or other agent mentions in automated prompts—this can trigger the UI version of agents. Let the routing handle which agent runs.

4. **Verify Before Marking Complete**: Only mark task checkboxes complete after verifying the implementation works.

Do not mark checklist items complete or dispatch new keepalive rounds until the acceptance criteria in the canonical guide are satisfied. Update all relevant documents together if the contract evolves.
