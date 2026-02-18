# Agent Runner Output Contract

**Version:** 1.0
**Status:** Canonical specification
**Last Updated:** February 17, 2026

## Purpose

This document defines the **required output contract** for all agent runner workflows in the Workflows repository. Any workflow that acts as an agent runner (e.g., `reusable-codex-run.yml`, `reusable-claude-run.yml`) MUST conform to this contract to ensure compatibility with:

- Keepalive loop orchestration
- Autofix workflows
- Verifier workflows
- Bot comment handlers
- Progress tracking and metrics

## Contract Compliance

**Current Implementations:**
- ✅ `reusable-codex-run.yml` — fully compliant
- ✅ `reusable-claude-run.yml` — fully compliant

**Future Implementations:**
- Any new agent runner (Gemini, GitHub Models, etc.) MUST implement this contract

---

## Required Inputs

All agent runners MUST accept these workflow_call inputs:

### Core Execution Parameters

| Input | Type | Required | Description |
|-------|------|----------|-------------|
| `skip` | boolean | false | If true, skip execution entirely (for conditional calls) |
| `prompt_file` | string | true | Path to prompt file the agent should read |
| `mode` | string | false | Agent mode for logging (keepalive \| autofix \| verifier) |
| `pr_number` | string | false | Pull request number (for logging/comments by callers) |
| `pr_ref` | string | false | Branch/ref to checkout and push to (e.g., refs/heads/feature-branch) |
| `base_ref` | string | false | Base branch/ref for conflict surfacing |

### Workflow Infrastructure

| Input | Type | Required | Description |
|-------|------|----------|-------------|
| `workflows_ref` | string | false | Ref of Workflows repo to checkout for scripts (default: main) |
| `max_runtime_minutes` | number | false | Upper bound for job runtime in minutes (default: 45) |
| `environment` | string | false | GitHub environment (agent-standard \| agent-high-privilege) |

### Agent Configuration

| Input | Type | Required | Description |
|-------|------|----------|-------------|
| `sandbox` | string | false | Sandbox mode (agent-specific interpretation) |
| `safety_strategy` | string | false | Safety strategy (agent-specific interpretation) |
| `appendix` | string | false | Optional context appended to prompt |
| `iteration` | string | false | Current iteration number (for tracking) |

**Note:** Agent-specific parameters (e.g., `codex_cli_version`, `codex_args`, `claude_cli_version`) are acceptable as additional inputs but MUST NOT be required for cross-agent compatibility.

---

## Required Outputs

All agent runners MUST provide these workflow_call outputs:

### Execution Results

| Output | Type | Description | Example |
|--------|------|-------------|---------|
| `final-message` | string | Full agent output message (base64 encoded) | `SGVsbG8gd29ybGQ=` |
| `final-message-summary` | string | First 500 chars of output (safe for PR comments) | `"Task completed successfully..."` |
| `exit-code` | string | Agent CLI exit code (0=success, non-zero=failure) | `"0"` |

### Change Tracking

| Output | Type | Description | Example |
|--------|------|-------------|---------|
| `changes-made` | string | Whether agent made file changes (`"true"` \| `"false"`) | `"true"` |
| `commit-sha` | string | SHA of commit if changes were pushed (empty if no commit) | `"abc123def456..."` |
| `files-changed` | string | Number of files changed by agent | `"3"` |

### Error Handling

| Output | Type | Description | Example |
|--------|------|-------------|---------|
| `error-summary` | string | Failure summary message (prefers agent output, falls back to preflight errors) | `"Authentication failed: invalid token"` |
| `error-category` | string | Error classification (transient \| auth \| resource \| logic \| unknown) | `"auth"` |
| `error-type` | string | Error origin (agent \| infrastructure \| auth \| unknown) | `"agent"` |
| `error-recovery` | string | Suggested recovery action | `"retry"` \| `"manual"` \| `"ignore"` |

### LLM Task Analysis

All runners MUST support LLM-based task completion analysis:

| Output | Type | Description | Example |
|--------|------|-------------|---------|
| `llm-analysis-run` | string | Whether LLM analysis was performed (`"true"` \| `"false"`) | `"true"` |
| `llm-provider` | string | LLM provider used (github-models \| openai \| anthropic \| regex-fallback) | `"github-models"` |
| `llm-model` | string | Specific model used (e.g., gpt-4o, claude-3-5-sonnet) | `"gpt-4o"` |
| `llm-confidence` | string | Confidence level of analysis (0.0-1.0 as string) | `"0.85"` |
| `llm-completed-tasks` | string | JSON array of completed task descriptions | `'["Add tests", "Fix bug"]'` |
| `llm-has-completions` | string | Whether any task completions were detected (`"true"` \| `"false"`) | `"true"` |

---

## Output Semantics

### Exit Code Interpretation

- `"0"` — Agent completed successfully (may or may not have made changes)
- `"1"` — Agent encountered errors (check `error-category` and `error-summary`)
- Other non-zero — Agent-specific error codes (should still populate error outputs)

### Changes Made Logic

`changes-made` should be `"true"` if and only if:
1. Agent modified one or more files in the working tree, AND
2. Changes were committed, AND
3. Commit was pushed to remote

**Edge cases:**
- Agent runs but makes no changes → `changes-made: "false"`, `exit-code: "0"`
- Agent crashes before completing → `changes-made: "false"`, `exit-code: "1"`
- Agent commits but push fails → `changes-made: "false"`, `exit-code: "1"`, `error-category: "infrastructure"`

### Error Category Guidelines

| Category | When to Use | Recovery |
|----------|-------------|----------|
| `transient` | Network issues, rate limits, temporary service outages | Retry |
| `auth` | Authentication/authorization failures | Manual fix (check secrets) |
| `resource` | Out of memory, disk space, quota exceeded | Manual fix (increase resources) |
| `logic` | Agent logic errors, invalid input, malformed prompts | Manual fix (review prompt/task) |
| `unknown` | Unclassified errors | Manual investigation |

### LLM Analysis Requirements

1. **Provider priority:**
   - Prefer GitHub Models (no external secrets)
   - Fallback to OpenAI if `OPENAI_API_KEY` available
   - Fallback to Anthropic if `CLAUDE_API_STRANSKE` available
   - Last resort: regex-based fallback (confidence: 0.5)

2. **Task extraction logic:**
   - Parse agent output for checkbox syntax: `- [x] Task description`
   - Extract PR body for original task list
   - Compare to determine completed tasks
   - Return JSON array of completed task descriptions

3. **Confidence scoring:**
   - `1.0` — LLM explicitly confirmed completions with high certainty
   - `0.8-0.9` — LLM inferred completions from agent output
   - `0.5-0.7` — Regex fallback detected checkbox changes
   - `0.0-0.4` — Low confidence or no analysis possible

---

## Caller Expectations

Workflows that invoke agent runners MUST:

1. **Handle skip parameter:**
   ```yaml
   with:
     skip: ${{ some_condition }}
   ```
   Runners should exit early with success if `skip: true`.

2. **Check exit-code before assuming success:**
   ```yaml
   if: needs.run-agent.outputs.exit-code == '0'
   ```

3. **Use changes-made for conditional logic:**
   ```yaml
   if: needs.run-agent.outputs.changes-made == 'true'
   ```

4. **Display error-summary in comments on failure:**
   ```yaml
   if: needs.run-agent.outputs.exit-code != '0'
   run: |
     echo "${{ needs.run-agent.outputs.error-summary }}"
   ```

5. **Respect error-recovery suggestions:**
   - `"retry"` → Add `agent:retry` label or re-dispatch
   - `"manual"` → Add `needs-human` label and notify
   - `"ignore"` → Continue without blocking

---

## Versioning and Evolution

### Adding New Outputs

New optional outputs MAY be added without breaking compatibility:
- Add output with default empty string value
- Update this document
- Update all existing runners to provide the output

### Deprecating Outputs

Existing outputs MUST NOT be removed. Instead:
1. Mark as deprecated in this document
2. Update callers to stop depending on deprecated output
3. After 3 months with no usage, remove from contract

### Breaking Changes

Breaking changes (e.g., changing output types, renaming outputs) require:
1. Major version bump of this contract (e.g., 1.0 → 2.0)
2. Migration guide for all callers
3. Phased rollout across Workflows + consumer repos

---

## Implementation Checklist

When implementing a new agent runner:

- [ ] Accept all required inputs (document any additional agent-specific inputs)
- [ ] Provide all required outputs (set empty string if value unavailable)
- [ ] Implement LLM-based task analysis (with fallbacks)
- [ ] Handle `skip: true` input gracefully
- [ ] Populate error outputs on all failure paths
- [ ] Test with keepalive, autofix, and verifier modes
- [ ] Update `.github/agents/registry.yml` with agent config
- [ ] Add to `tests/workflows/test_workflow_naming.py`
- [ ] Sync to consumer templates via `templates/consumer-repo/`

---

## Examples

### Successful Run (No Changes)

```yaml
final-message: "SW5zcGVjdGVkIGNvZGVi..." # (base64)
final-message-summary: "Inspected codebase. No changes needed."
exit-code: "0"
changes-made: "false"
commit-sha: ""
files-changed: "0"
error-summary: ""
error-category: ""
error-type: ""
error-recovery: ""
llm-analysis-run: "true"
llm-provider: "github-models"
llm-model: "gpt-4o"
llm-confidence: "0.9"
llm-completed-tasks: '[]'
llm-has-completions: "false"
```

### Successful Run (With Changes)

```yaml
final-message: "Q29tbWl0dGVkIGNoYW5..." # (base64)
final-message-summary: "Committed changes to 3 files."
exit-code: "0"
changes-made: "true"
commit-sha: "abc123def456789"
files-changed: "3"
error-summary: ""
error-category: ""
error-type: ""
error-recovery: ""
llm-analysis-run: "true"
llm-provider: "github-models"
llm-model: "gpt-4o"
llm-confidence: "0.95"
llm-completed-tasks: '["Add unit tests", "Fix typo in README"]'
llm-has-completions: "true"
```

### Failed Run (Auth Error)

```yaml
final-message: ""
final-message-summary: ""
exit-code: "1"
changes-made: "false"
commit-sha: ""
files-changed: "0"
error-summary: "Authentication failed: CODEX_AUTH_JSON is invalid or expired"
error-category: "auth"
error-type: "agent"
error-recovery: "manual"
llm-analysis-run: "false"
llm-provider: ""
llm-model: ""
llm-confidence: ""
llm-completed-tasks: '[]'
llm-has-completions: "false"
```

---

## See Also

- [Provider-Agnostic Coding Agents Plan](https://github.com/stranske/Workflows/blob/main/docs/plans/provider-agnostic-coding-agents.md)
- [Agent Registry Schema](../../.github/agents/registry.yml)
- [Keepalive Goals and Plumbing](https://github.com/stranske/Workflows/blob/main/docs/keepalive/GoalsAndPlumbing.md)
- [Multi-Agent Routing Architecture](https://github.com/stranske/Workflows/blob/main/docs/keepalive/MULTI_AGENT_ROUTING.md)

---

**Canonical Source:** This document is the authoritative specification for agent runner outputs. When implementing or debugging agent runners, refer to this document first.
