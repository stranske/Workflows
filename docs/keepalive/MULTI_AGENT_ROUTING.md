# Multi-Agent Routing Architecture

**Status:** Active registry-driven routing
**Related:** `GoalsAndPlumbing.md`, `Observability_Contract.md`

This document describes the multi-agent routing architecture that enables different AI agents (Codex CLI, Claude, etc.) to work on PRs through a unified keepalive loop.

---

## Overview

The keepalive system routes work to different agents based on the `agent:*` label on a PR:

| Label | Agent | Workflow |
|-------|-------|----------|
| `agent:codex` | Codex CLI | `reusable-codex-run.yml` |
| `agent:claude` | Claude CLI | `reusable-claude-run.yml` |
| `agent:cursor` | Cursor | `reusable-cursor-run.yml` |
| `agent:muse` | Muse | `reusable-muse-run.yml` |
| `agent:gemini` | Gemini | `reusable-gemini-run.yml` |

The [agent registry](../../.github/agents/registry.yml) declares runner
capabilities, credentials and execution profiles. Look up the selected Codex
profile there for its requested model, fallback and reasoning effort.

The Muse runner sets both Git author and committer to `muse
<muse@users.noreply.github.com>` in the `Run Muse` environment so CLI-created
commits retain the producing agent's identity. Durability export resolves Muse
from its concrete `agent:muse` / `runner:muse` label or `muse/` branch; the
Orchestrator feedback ledger records the explicitly selected agent, rather than
inferring it from the GitHub account that pushes. After delivery, inspect the
next native Muse commit with `gh api repos/OWNER/REPO/commits/SHA --jq .commit`
and retain both author and committer fields. Local Git tests prove environment
precedence over repository defaults; they do not establish a native Muse run.

---

## How It Works

1. A Gate, label, manual or [sweep](GoalsAndPlumbing.md#periodic-re-evaluation-keepalive-sweep)
   wake reaches the Workflows keepalive loop or the consumer's Gate Followups.
2. [`evaluateKeepaliveLoop`](../../.github/scripts/keepalive_loop.js) evaluates
   the PR and uses its concrete `agent:<name>` label. With `agent:auto`, the
   [delegation policy](../../.github/scripts/agent_delegation_policy.js)
   also evaluates capacity, provider backoff and possible rotation.
3. The evaluator extracts the Scope, Tasks, Acceptance Criteria and current
   progress. The hosted jobs supply the task appendix to the worker as an
   artifact. See the [prompt delivery contract](GoalsAndPlumbing.md#6-instruction-prompt-contract).
4. The selected provider's worker runs after admission and credential checks.
   `finish` reconciles state and records the observed worker outcome.

## Key Components

### Runner jobs

The [Workflows loop](../../.github/workflows/agents-keepalive-loop.yml) and
[consumer Gate Followups](../../templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml)
declare one guarded job each for `run-codex`, `run-claude`, `run-cursor`,
`run-muse` and `run-gemini`. Each job checks the evaluator's selected
`agent_type` and calls its matching reusable workflow. The
[`keepalive_prompt_routing.js`](../../.github/scripts/keepalive_prompt_routing.js)
helper selects the work, fix or verification prompt.

### Agent-Agnostic Prompt

The [implementation prompt](../../.github/codex/prompts/keepalive_next_task.md)
uses the appended scope and checklist. It asks the selected worker to advance
the first unchecked task it can complete and verify. Agent mentions can
trigger the separate comment-command path.
---

## Adding Another Agent

The high-level work for another agent is:

1. Add a registry entry in `.github/agents/registry.yml`.
2. Add a reusable runner workflow modeled after the Codex and Claude runners.
3. Wire a `run-<agent>` job into both hosted entry points and pass the runner outputs to `finish`.
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

The Automated Status Summary can display:
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

- [Evaluator and task appendix tests](../../.github/scripts/__tests__/keepalive-loop.test.js)
- [Prompt routing tests](../../.github/scripts/__tests__/keepalive-prompt-routing.test.js)
- [Root and consumer job shape tests](../../tests/workflows/test_keepalive_job_shape.py)
- [Registry and model profile tests](../../.github/scripts/__tests__/keepalive-model-profile-contract.test.js)
