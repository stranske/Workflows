# Multi-Agent Routing Architecture

**Status:** Adopted  
**Related:** `GoalsAndPlumbing.md`, `Observability_Contract.md`

This document describes the multi-agent routing architecture that enables different AI agents (Codex CLI, Claude, etc.) to work on PRs through a unified keepalive loop.

---

## Overview

The keepalive system routes work to different agents based on the `agent:*` label on a PR:

| Label | Agent | Workflow |
|-------|-------|----------|
| `agent:codex` | Codex CLI (gpt-5.2-codex) | `reusable-codex-run.yml` |
| `agent:claude` | Claude (future) | `reusable-claude-run.yml` |
| `agent:gemini` | Gemini (future) | `reusable-gemini-run.yml` |

---

## How It Works

```
PR with agent:codex label
    ↓
Gate CI passes
    ↓
agents-keepalive-loop.yml triggers
    ↓
Evaluate step extracts:
  - agentType = "codex" (from agent:codex label)
  - taskAppendix = extracted Scope/Tasks/Acceptance
    ↓
Routes to run-codex job (conditional on agentType)
    ↓
Codex receives prompt + task appendix:
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

### 3. Conditional Routing (`agents-keepalive-loop.yml`)

```yaml
run-codex:
  name: Keepalive next task (Codex)
  if: needs.evaluate.outputs.agent_type == 'codex'
  uses: stranske/Workflows/.github/workflows/reusable-codex-run.yml@main
  with:
    appendix: ${{ needs.evaluate.outputs.task_appendix }}
    ...

# Future: run-claude:
#   if: needs.evaluate.outputs.agent_type == 'claude'
#   uses: stranske/Workflows/.github/workflows/reusable-claude-run.yml@main
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

## Adding a New Agent

To add support for a new agent (e.g., Claude):

### 1. Create the reusable workflow

Create `.github/workflows/reusable-claude-run.yml` following the pattern of `reusable-codex-run.yml`:
- Accept same inputs (prompt_file, appendix, pr_number, pr_ref)
- Emit same outputs (final-message, exit-code, changes-made, commit-sha, files-changed)

### 2. Add conditional job in keepalive loop

```yaml
run-claude:
  name: Keepalive next task (Claude)
  needs:
    - evaluate
    - preflight
  if: needs.evaluate.outputs.agent_type == 'claude'
  uses: stranske/Workflows/.github/workflows/reusable-claude-run.yml@main
  secrets:
    CLAUDE_API_KEY: ${{ secrets.CLAUDE_API_KEY }}
  with:
    skip: ${{ needs.evaluate.outputs.action != 'run' }}
    prompt_file: .github/codex/prompts/keepalive_next_task.md
    pr_number: ${{ needs.evaluate.outputs.pr_number }}
    pr_ref: ${{ needs.evaluate.outputs.pr_ref }}
    appendix: ${{ needs.evaluate.outputs.task_appendix }}
```

### 3. Update summary job

Add the new agent's outputs to the summary job's needs and pass through to `updateKeepaliveLoopSummary`:

```yaml
summary:
  needs:
    - evaluate
    - preflight
    - run-codex
    - run-claude  # Add new agent
```

### 4. Create GitHub label

Create `agent:claude` label in the repository.

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

- [x] Add output for `final-message` from Codex action
- [x] Add output for `files-changed`
- [ ] Write iteration summary to GITHUB_STEP_SUMMARY  ← WORK ON THIS
- [ ] Create new section in PR body for CLI Codex status
...

### Acceptance Criteria
The PR is complete when ALL of these are satisfied:

- [ ] CLI Codex iterations are visible in the PR body
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
