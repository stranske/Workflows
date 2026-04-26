# Multi-Agent Routing Architecture

**Status:** Active registry-driven routing
**Related:** `GoalsAndPlumbing.md`, `Observability_Contract.md`

This document describes the multi-agent routing architecture that enables different AI agents (Codex CLI, Claude, etc.) to work on PRs through a unified keepalive loop.

---

## Overview

The keepalive system routes work to different agents based on the `agent:*` label on a PR:

| Label | Agent | Workflow |
|-------|-------|----------|
| `agent:codex` | Codex CLI (gpt-5.3-codex) | `reusable-codex-run.yml` |
| `agent:claude` | Claude CLI | `reusable-claude-run.yml` |

The authoritative list lives in `.github/agents/registry.yml`; update that registry and the matching runner workflow before adding labels to this table.

---

## How It Works

```
PR with agent:<name> label
    ↓
Gate CI passes
    ↓
agents-keepalive-loop.yml triggers
    ↓
Evaluate step extracts:
  - agentType = "<name>" (from agent:<name> label)
  - taskAppendix = extracted Scope/Tasks/Acceptance
    ↓
Routes through the registry-backed runner for agentType
    ↓
The selected agent receives prompt + task appendix:
  "Your objective is to satisfy the Acceptance Criteria...
   ---
   ## PR Tasks and Acceptance Criteria
   **Progress:** 3/10 tasks complete, 7 remaining
   ### Tasks
   - [ ] First unchecked task ← Work on this
   ..."
    ↓
Agent works, commits, pushes
    ↓
Summary updated with agent-specific output
```

---

## Key Components

### 1. Agent Label Extraction (`keepalive_loop.js`)

```javascript
// Extract agent type from agent:* labels
const agentLabel = labels.find((label) => label.startsWith('agent:'));
const agentType = agentLabel ? agentLabel.replace('agent:', '') : '';
```

The `evaluateKeepaliveLoop` function returns:
- `agentType` - The agent identifier (e.g., "codex", "claude")
- `taskAppendix` - Formatted tasks for injection into the prompt
- `hasAgentLabel` - Whether any `agent:*` label exists

### 2. Task Appendix Builder (`keepalive_loop.js`)

```javascript
function buildTaskAppendix(sections, checkboxCounts) {
  // Builds structured task context:
  // - Progress summary (X/Y complete)
  // - Scope section (if present)
  // - Tasks with checkboxes
  // - Acceptance criteria
}
```

The appendix is injected directly into the agent prompt so tasks are explicit, not implied.

### 3. Registry-Backed Routing (`agents-keepalive-loop.yml`)

```yaml
run-selected-agent:
  # Conceptual example: the live workflow resolves runner metadata from
  # .github/agents/registry.yml and dispatches the matching reusable runner.
  if: needs.evaluate.outputs.agent_type != ''
  with:
    appendix: ${{ needs.evaluate.outputs.task_appendix }}
    agent_type: ${{ needs.evaluate.outputs.agent_type }}
    ...
```

### 4. Agent-Agnostic Prompt (`keepalive_next_task.md`)

The prompt is written to be agent-agnostic:

```markdown
# Keepalive Next Task

Your objective is to satisfy the **Acceptance Criteria** by completing each **Task** within the defined **Scope**.

**This round you MUST:**
1. Implement actual code or test changes that advance at least one incomplete task
2. Commit meaningful source code—not just status/docs updates
3. Mark a task checkbox complete ONLY after verifying the implementation works
4. Focus on the FIRST unchecked task unless blocked

**The Tasks and Acceptance Criteria are provided in the appendix below.**
```

No `@codex` or agent-specific mentions—the routing determines which agent receives it.

---

## Adding Another Agent

The high-level work for another agent is:

1. Add a registry entry in `.github/agents/registry.yml`.
2. Add a reusable runner workflow modeled after the Codex and Claude runners.
3. Wire any new runner outputs through the keepalive summary step.
4. Document the new label, required secrets, and readiness/preflight ownership.

---

## Why Task Injection Matters

Previously, agents received a vague prompt: "Read the PR body for tasks." This led to:
- Agents doing useful but **unrelated** work
- Agents fixing CI failures instead of PR tasks
- No accountability for completing assigned tasks

Now, tasks are **explicitly injected** into the prompt appendix:

```markdown
---
## PR Tasks and Acceptance Criteria

**Progress:** 3/10 tasks complete, 7 remaining

### Tasks
Complete these in order. Mark checkbox done ONLY after implementation is verified:

- [x] Add output for `final-message` from the agent action
- [x] Add output for `files-changed`
- [ ] Write iteration summary to GITHUB_STEP_SUMMARY  ← WORK ON THIS
- [ ] Create new section in PR body for CLI agent status
...

### Acceptance Criteria
The PR is complete when ALL of these are satisfied:

- [ ] CLI agent iterations are visible in the PR body
- [ ] Each iteration shows: round number, tasks attempted, outcome
...
---
```

This makes the agent's objective unambiguous and measurable.

---

## Observability

The keepalive summary comment displays:
- **Agent name**: Shows which agent is working (e.g., "Codex", "Claude")
- **Last run details**: Exit code, files changed, commit SHA
- **Agent output**: First 300 chars of agent response
- **Failure tracking**: Consecutive failures and threshold

Example summary header:
```
**PR #103** | Agent: **Codex** | Iteration **3/5**
```

---

## Testing

Tests for multi-agent routing are in `.github/scripts/__tests__/keepalive-loop.test.js`:

```javascript
test('evaluateKeepaliveLoop extracts agent type from agent:* labels', async () => {
  // PR with agent:claude label
  const result = await evaluateKeepaliveLoop({ ... });
  assert.equal(result.agentType, 'claude');
  assert.equal(result.hasAgentLabel, true);
});

test('buildTaskAppendix formats scope, tasks, and acceptance criteria', () => {
  const appendix = buildTaskAppendix(sections, checkboxCounts);
  assert.ok(appendix.includes('## PR Tasks and Acceptance Criteria'));
  assert.ok(appendix.includes('**Progress:** 1/4 tasks complete'));
});
```
