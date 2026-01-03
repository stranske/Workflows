# Keepalive — Goals & Plumbing (Canonical Reference)

> **Audience:** Human maintainers and automation agents responsible for the keepalive workflow. Review this document **before** touching any keepalive logic or dispatch plumbing.

## Quick Navigation
- [Purpose & Scope](#purpose--scope)
- [Lifecycle Overview](#lifecycle-overview)
- [1. Activation Guardrails](#1-activation-guardrails)
- [2. Repeat Contract](#2-repeat-contract)
- [3. Run Cap Enforcement](#3-run-cap-enforcement)
- [4. Pause & Stop Controls](#4-pause--stop-controls)
- [5. No-Noise Policy](#5-no-noise-policy)
- [6. Instruction Prompt Contract](#6-instruction-prompt-contract)
- [7. Agent Routing](#7-agent-routing)
- [8. Branch-Sync Gate](#8-branch-sync-gate)
- [9. Orchestrator Invariants](#9-orchestrator-invariants)
- [10. Restart & Success Conditions](#10-restart--success-conditions)
- [11. Issue Context & Status Summary](#11-issue-context--status-summary)
- [12. Progress Detection & Checkbox Reconciliation](#12-progress-detection--checkbox-reconciliation)
- [Appendix: Operator Checklist](#appendix-operator-checklist)

---

## Purpose & Scope

- **Purpose:** Maintain a safe, iterative loop where keepalive nudges an agent through small, verifiable increments on a PR until every acceptance criterion is complete—while guaranteeing predictable behaviour and safety rails.
- **Scope:** Activation requirements, dispatch plumbing, throttling, branch-sync guarantees, and shutdown rules for the GitHub PR keepalive workflow.
- **Non-goals:** Guidance for automation unrelated to keepalive.

---

## Lifecycle Overview

1. **PR labeled:** A PR receives an `agent:*` label (e.g., `agent:codex`, `agent:claude`).
2. **Guarded check:** Orchestrator guardrails confirm the label, Gate success, and run-cap capacity before running the agent.
3. **Agent execution:** The appropriate agent workflow runs with explicit task context injected into the prompt.
4. **Timed repeats:** Subsequent Gate completions trigger re-evaluation and continue if tasks remain.
5. **Definition of done:** As soon as the acceptance criteria are all checked complete, keepalive posts no further rounds.
6. **Suspend on label change:** If the label disappears or the guardrails fail mid-run, the workflow records the skip reason and stays silent until a human re-applies the label.

---

## 1. Activation Guardrails

Keepalive **must not** dispatch an agent unless *all* conditions hold:

1. **PR opt-in:** The PR carries an `agent:*` label (e.g., `agent:codex`, `agent:claude`).
2. **Gate green:** The Gate workflow for the current head SHA completed successfully.
3. **Tasks present:** The PR body contains unchecked tasks in the Automated Status Summary.

> **Multi-Agent Note:** The `agent:*` label determines which agent workflow runs. See [`MULTI_AGENT_ROUTING.md`](MULTI_AGENT_ROUTING.md) for details.

---

## 2. Repeat Contract

Before the next agent run:

- Re-validate the activation guardrails.
- Confirm the concurrent run cap is still available (see Section 3).
- Check failure tracking—pause after repeated failures.

If any requirement fails, keepalive stays silent—no PR comments. Operators may record the skip reason in run summaries only.

---

## 3. Run Cap Enforcement

- **Default limit:** Maximum of **1** concurrent agent run per PR.
- **Label override:** Respect `agents:max-parallel:<K>` when present (integer 1–5).
- **Enforcement:** Dispatch only when the count of in-progress runs is `< K`. If at cap, exit quietly after updating the run summary.

---

## 4. Pause & Stop Controls

- Removing the `agent:*` label halts new dispatches until a label is re-applied and all guardrails pass again.
- Respect the stronger `agents:pause` label, which blocks *all* keepalive activity.
- After repeated failures (default: 3), the loop pauses and adds `needs-human` label.

**To resume after failure:**
1. Investigate the failure reason in the keepalive summary comment
2. Fix any issues in the code or prompt
3. Remove the `needs-human` label
4. The next Gate pass will restart the loop

Or manually edit the keepalive summary comment to reset `failure: {}` in the state marker.

---

## 5. No-Noise Policy

When preconditions are missing (labels absent, Gate not green, run cap reached), keepalive must not add new PR comments. At most, log a concise operator summary explaining the skipped action.

---

## 6. Instruction Prompt Contract

When running is allowed:

1. **Task injection:** The prompt includes an appendix with explicitly extracted Scope, Tasks, and Acceptance Criteria from the PR body.
2. **Agent-agnostic prompt:** The base prompt (`.github/codex/prompts/keepalive_next_task.md`) is agent-agnostic—no `@codex` or agent mentions.
3. **Progress tracking:** The appendix includes progress count (e.g., "3/10 tasks complete, 7 remaining").

Example prompt appendix:
```markdown
---
## PR Tasks and Acceptance Criteria

**Progress:** 3/10 tasks complete, 7 remaining

### Scope
Add visibility for CLI Codex iterations in the PR body.

### Tasks
Complete these in order. Mark checkbox done ONLY after implementation is verified:

- [x] Add output for `final-message` from Codex action
- [ ] Write iteration summary to GITHUB_STEP_SUMMARY
- [ ] Create new section in PR body for CLI Codex status
...

### Acceptance Criteria
The PR is complete when ALL of these are satisfied:

- [ ] CLI Codex iterations are visible in the PR body
...
---
```

---

## 7. Agent Routing

The keepalive loop routes to different agent workflows based on the `agent:*` label:

| Label | Agent | Workflow |
|-------|-------|----------|
| `agent:codex` | Codex CLI (gpt-5.2-codex) | `reusable-codex-run.yml` |
| `agent:claude` | Claude (future) | `reusable-claude-run.yml` |
| `agent:gemini` | Gemini (future) | `reusable-gemini-run.yml` |

See [`MULTI_AGENT_ROUTING.md`](MULTI_AGENT_ROUTING.md) for implementation details and how to add new agents.

---

## 8. Branch-Sync Gate

Before the next round begins:

1. Verify that the PR head SHA changed after the agent reported "done".
2. If unchanged, the agent may have failed to push. The loop will retry on the next Gate pass.
3. After repeated failures (default: 3), pause and add `needs-human` label with instructions for recovery.

---

## 9. Orchestrator Invariants

- **No self-cancellation:** Configure concurrency as `keepalive-{pr}` with `cancel-in-progress: false`.
- **Explicit bails:** For early exits (missing preconditions, run cap reached, Gate not green), write a one-line reason to the run summary.
- **Summary comment:** Update the keepalive summary comment with iteration status, agent output preview, and failure tracking.

---

## 10. Restart & Success Conditions

- Removing and re-applying the `agent:*` label restarts the workflow once the activation guardrails pass again.
- To reset failure count: edit the keepalive summary comment and set `failure: {}` in the state marker, or remove `needs-human` label.
- Keepalive stands down when **all acceptance criteria are checked complete**. At that point the orchestrator stops issuing further rounds.

---

## 11. Issue Context & Status Summary

The Keepalive workflow depends on the **Automated Status Summary** block in the PR body to extract Scope, Tasks, and Acceptance Criteria.

### Data Flow
1. **Issue Intake:** Creates a PR with the Issue content embedded.
2. **PR Meta Update:** `agents-pr-meta` workflow parses the source Issue for Scope/Tasks/Acceptance and generates the Automated Status Summary block.
3. **Keepalive Execution:** The keepalive loop extracts tasks from the Automated Status Summary and injects them into the agent prompt via the task appendix.

### Failure Modes & Recovery
- **Missing Link:** If the PR lacks the Issue Number, add `#<issue_number>` to the PR body.
- **Missing Sections:** If the source Issue lacks "Scope"/"Tasks"/"Acceptance", update the source Issue text.
- **No Tasks:** If no checkboxes are found, keepalive will stop with reason `no-checklists`.

---

## 12. Progress Detection & Checkbox Reconciliation

Keepalive now has two ways to detect task completion and keep PR checkboxes in sync:

1. **Session analysis (preferred):** After an agent run, `scripts/analyze_codex_session.py` analyzes the Codex JSONL session via `tools/codex_session_analyzer.py`. If an LLM provider is available, it returns a list of completed tasks plus quality signals (confidence, data quality, effort score).
2. **Commit/file analysis (fallback):** `.github/scripts/keepalive_loop.js` runs `analyzeTaskCompletion()` to match commits and changed files against unchecked tasks when LLM data is unavailable or incomplete.

### Auto-Update Rules
- **Auto-check only high confidence matches.** Low/medium confidence matches are logged but not applied.
- **Apply only to existing task/acceptance checkboxes.** Scope remains informational and is not mutated.
- **No changes when evidence is weak.** If no high-confidence matches exist, the PR body is left untouched.

### Operational Notes
- The keepalive summary comment flags when files changed but no checkboxes were updated, prompting the next iteration to reconcile tasks.
- The reconciliation step uses the same task text from the Automated Status Summary to avoid accidental mismatch.
- LLM analysis is optional; if unavailable, the commit/file matcher remains active.

---

## Appendix: Operator Checklist

| Phase | Key Checks |
|-------|------------|
| Activation | `agent:*` label present · Gate success |
| Repeat | Activation guardrails still true · run cap respected · failure threshold not exceeded |
| Routing | Correct agent workflow triggered based on label |
| Prompt | Task appendix injected · Progress visible |
| Exit | All acceptance criteria satisfied or max iterations reached |

Keep this document in sync with [`MULTI_AGENT_ROUTING.md`](MULTI_AGENT_ROUTING.md) and [`Observability_Contract.md`](Observability_Contract.md) whenever the workflow evolves.
