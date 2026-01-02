# LangChain Keepalive Integration Plan

> **Status**: Planning
> **Created**: 2026-01-02
> **Target Branch**: `feature/langchain-analysis`
> **Test Consumer**: `stranske/Portable-Alpha-Extension-Model`

---

## Summary of Findings

### 1. Session Data Sources (Multiple Options!)

We discovered **three different data sources** from the Codex CLI, each with different richness levels:

#### Option A: Final Summary (`--output-last-message`) - Current
**Current state**: We capture via `codex-output-*.md` artifacts.
- Uploaded by `reusable-codex-run.yml` line 553
- Contains Codex's final summary message only
- Artifact name format: `codex-output-{pr_number}`

**Pros**: Simple, low data volume
**Cons**: Limited context, misses intermediate steps

---

#### Option B: JSONL Event Stream (`--json`) - **Recommended**
The Codex CLI has a `--json` flag that streams **detailed events as JSONL**:

```bash
codex exec --json --output-last-message "$OUTPUT_FILE" "$PROMPT" 2>&1 | tee "$SESSION_LOG"
```

**Event types available** (from [exec.md](https://github.com/openai/codex/blob/main/docs/exec.md#json-output-mode)):
- `thread.started` / `turn.started` / `turn.completed` / `turn.failed`
- `item.started` / `item.updated` / `item.completed`

**Item types**:
| Type | Contains | LLM Analysis Potential |
|------|----------|----------------------|
| `agent_message` | Assistant responses | ⭐⭐⭐ High - explicit completion statements |
| `reasoning` | Model thinking summaries | ⭐⭐⭐ High - reveals intent and progress |
| `command_execution` | Shell commands + exit codes + output | ⭐⭐ Medium - shows actual work done |
| `file_change` | Files added/modified/deleted | ⭐⭐ Medium - concrete evidence |
| `mcp_tool_call` | MCP tool invocations | ⭐ Low - implementation detail |
| `web_search` | Web search actions | ⭐ Low - implementation detail |
| `todo_list` | Task tracking | ⭐⭐⭐ High - direct task mapping! |

**Known issues** (from GitHub):
- [#4776](https://github.com/openai/codex/issues/4776): Field names changed (`item_type`→`type`, `assistant_message`→`agent_message`)
- [#5276](https://github.com/openai/codex/issues/5276): Reasoning token usage not yet in output
- Schema may evolve - need graceful parsing

**Pros**: Rich data, shows reasoning and progress, includes todo tracking!
**Cons**: More data to process, schema changes over time

---

#### Option C: Session Files (`~/.codex/sessions/`)
Full session history saved to disk:
```
~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl
```

**Pros**: Most complete data, includes full token counts
**Cons**: Requires file system access post-run, may not persist in CI

---

#### Option D: TUI Session Recording (`CODEX_TUI_RECORD_SESSION=1`)
Environment variable enables detailed logging:
```bash
CODEX_TUI_RECORD_SESSION=1 codex ...
# Logs to ~/.codex/log/session-YYYYMMDDTHHMMSSZ.jsonl
```

**Pros**: Captures all TUI events
**Cons**: Designed for interactive mode, may not work with `codex exec`

---

### Data Source Selection for Testing

| Phase | Data Source | Why |
|-------|-------------|-----|
| Test 1 | Option A (summary only) | Baseline comparison |
| Test 2 | Option B (`--json` stream) | Recommended - rich + practical |
| Test 3 | Option B subset | Only `agent_message` + `reasoning` + `todo_list` |

**Priority fields for analysis**:
1. `agent_message` - What did Codex say it accomplished?
2. `reasoning` - What was it thinking?
3. `todo_list` - Direct mapping to PR checkboxes!
4. `file_change` - Concrete evidence of work

### 2. GitHub Models API ✅

**Verified working** with your GitHub token:
```bash
curl -s "https://models.inference.ai.azure.com/chat/completions" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"test"}],"model":"gpt-4o-mini"}'
```

**Integration approach**: Use LangChain's OpenAI integration with custom base URL:
```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="gpt-4o-mini",
    base_url="https://models.inference.ai.azure.com",
    api_key=os.environ["GITHUB_TOKEN"],  # GitHub token works!
)
```

No separate `langchain-github` package needed.

---

## Community Tools & Research

### Existing Codex Session Analysis Tools

| Tool | Description | Relevance |
|------|-------------|-----------|
| [codex-session-view](https://github.com/AcidicSoil/codex-session-view) | Visualizer with **AI Session Coach** that analyzes sessions using LLM | ⭐⭐⭐ Reference implementation! |
| [codex-history-list](https://github.com/shinshin86/codex-history-list) | CLI to list sessions, extracts cwd and first user request | ⭐⭐ Parsing patterns |
| [codex_usage_report](https://github.com/rubens-amaral/codex_usage_report) | Go CLI analyzing session logs for rate limits | ⭐ Token tracking |
| [cxusage](https://github.com/zaharsyahrafi/cxusage) | Daily usage aggregation from session logs | ⭐ Aggregation patterns |

**Key insight from `codex-session-view`**: Uses AI Session Coach with multiple providers (OpenAI, Gemini, LM Studio) - validates our provider fallback approach!

### LangChain Integration Patterns

**No direct Codex→LangChain library exists**, but relevant LangChain components:

| Component | Use Case |
|-----------|----------|
| `TrajectoryEvalChain` | Evaluates agent step sequences - similar to our task completion analysis |
| `LogStreamCallbackHandler` | Real-time event streaming - pattern for processing JSONL |
| `FileCallbackHandler` | Persists agent actions - reference for our logging |

**LangChain trajectory format** (from `trajectory_eval_chain.py`):
```python
def get_agent_trajectory(steps: Sequence[tuple[AgentAction, str]]) -> str:
    return "\n\n".join([
        f"""Step {i}:
Tool used: {action.tool}
Tool input: {action.tool_input}
Tool output: {output}"""
        for i, (action, output) in enumerate(steps, 1)
    ])
```

This pattern maps well to Codex JSONL events!

### Gap Analysis

- ❌ No existing Codex JSONL → LangChain message converter
- ❌ Python SDK for Codex still proposed ([#5320](https://github.com/openai/codex/issues/5320))
- ✅ Community has validated LLM-based session analysis approach
- ✅ Our provider fallback matches `codex-session-view` pattern

---

## Provider Fallback Chain

```
┌─────────────────────────────────────────┐
│  1. GitHub Models API (gpt-4o-mini)     │
│     - Uses existing GITHUB_TOKEN        │
│     - Free with Copilot subscription    │
├─────────────────────────────────────────┤
│  2. OpenAI API (gpt-4o-mini)            │
│     - Uses OPENAI_API_KEY secret        │
│     - ~$0.0006 per analysis             │
├─────────────────────────────────────────┤
│  3. Regex Fallback                      │
│     - No API calls                      │
│     - Basic pattern matching            │
└─────────────────────────────────────────┘
```

---

## Analysis Timing Options

| Option | When | Pros | Cons |
|--------|------|------|------|
| **A: Every round** | After each Codex run | Most accurate, catches all completions | Higher API usage |
| **B: On stall** | After round with no checkbox changes | Targeted intervention | Delays detection by 1 round |
| **C: Conditional** | Round 1 always, then only on stall | Balances accuracy vs cost | More logic complexity |
| **D: Post-CI** | After CI completes | Can correlate CI results with tasks | Adds latency |

**Testing plan**: Run A vs C to measure cost/benefit trade-off.

---

## Dependencies to Add

```toml
# pyproject.toml [project.optional-dependencies]
langchain = [
    "langchain-core>=0.3.0",
    "langchain-openai>=0.3.0",
]
```

**Note**: Keep as optional dependency so workflows without LLM still function.

---

## Files to Create/Modify

### New Files in `tools/`

| File | Purpose |
|------|---------|
| `llm_provider.py` | Provider abstraction with GitHub → OpenAI → regex fallback |
| `langchain_task_extractor.py` | LLM-enhanced task/scope extraction |
| `codex_log_analyzer.py` | Session output analysis for completion detection |
| `ci_failure_triage.py` | CI failure classification and fix suggestions |
| `update_pr_checkboxes.py` | GitHub API wrapper to update PR body checkboxes |
| `post_progress_comment.py` | Posts analysis comment when work incomplete |

### Workflow Modifications

| File | Change |
|------|--------|
| `.github/workflows/reusable-codex-run.yml` | Add post-run analysis step |
| `.github/scripts/keepalive_loop.js` | Inject analysis into next prompt |

---

## Testing Plan

### Phase 0: Data Source Evaluation

**Goal**: Determine which session data source provides best signal-to-noise for task completion detection.

| Test | Data Source | Method |
|------|-------------|--------|
| **0.1** | Summary only (Option A) | Current `--output-last-message` |
| **0.2** | Full JSONL (Option B) | `--json` piped to file |
| **0.3** | Filtered JSONL | Only `agent_message` + `reasoning` + `todo_list` events |

**Evaluation criteria**:
- Can the LLM accurately detect task completion?
- What's the token cost per analysis?
- How robust is parsing to schema changes?

**Workflow change for Option B**:
```yaml
# Current:
codex exec --output-last-message "$OUTPUT_FILE" "$PROMPT"

# Enhanced:
codex exec --json --output-last-message "$OUTPUT_FILE" "$PROMPT" 2>&1 | tee "$SESSION_JSONL"
# Then parse $SESSION_JSONL for rich analysis
```

---

### Phase 1: Baseline (Current System)

1. Create test issue in Portable Alpha with 3-4 tasks
2. Let keepalive run with current regex-only system
3. Record:
   - Total rounds to actual completion
   - Rounds to checkbox detection
   - False negatives (work done, not detected)

### Phase 2: LangChain Enhanced

1. Push `feature/langchain-analysis` branch to Workflows
2. Update Portable Alpha to use:
   ```yaml
   uses: stranske/Workflows/.github/workflows/reusable-codex-run.yml@feature/langchain-analysis
   ```
3. Add `OPENAI_API_KEY` secret to Portable Alpha (fallback)
4. Create similar test issue
5. Record same metrics

### Phase 3: Analysis

| Metric | Regex-Only | LangChain | Improvement |
|--------|------------|-----------|-------------|
| Rounds to completion | ? | ? | ? |
| Detection accuracy | ? | ? | ? |
| False positives | ? | ? | ? |
| API cost per PR | $0 | ~$0.01 | -$0.01 |
| Time per round | ? | +2-3s | Negligible |

---

## Implementation Steps

### Step 1: Add LangChain dependencies
- Update `pyproject.toml` with optional `[langchain]` extras
- Create `tools/llm_provider.py` with fallback logic

### Step 2: Port and adapt tools
- Copy tools from Trend Model Project (already retrieved to /tmp)
- Adapt to use `llm_provider.py` abstraction
- Add tests

### Step 3: Workflow integration
- Add analysis step to `reusable-codex-run.yml`
- Wire analysis results to PR checkbox updates
- Wire analysis results to next-round prompt

### Step 4: Consumer setup
- Update Portable Alpha workflow reference
- Add `OPENAI_API_KEY` secret
- Create test issue

### Step 5: Run comparison tests
- Execute Phase 1 (baseline)
- Execute Phase 2 (enhanced)
- Document results

### Step 6: Tune and finalize
- Decide on timing option (A/B/C/D)
- Merge to main
- Revert consumer to `@main`

---

## Secrets Required

| Secret | Repo | Purpose |
|--------|------|---------|
| `OPENAI_API_KEY` | Portable Alpha | Fallback LLM provider |
| `GITHUB_TOKEN` | Auto-provided | GitHub Models API (primary) |

---

## Codex JSONL Event Schema Reference

Based on [exec.md](https://github.com/openai/codex/blob/main/docs/exec.md) and source code analysis.

### Thread/Turn Events
```json
{"type": "thread.started", "thread_id": "uuid", "timestamp": "..."}
{"type": "turn.started", "turn_id": "uuid", "thread_id": "uuid"}
{"type": "turn.completed", "turn_id": "uuid", "token_usage": {...}}
{"type": "turn.failed", "turn_id": "uuid", "error": "..."}
```

### Item Events
```json
{"type": "item.started", "item_id": "uuid", "item_type": "agent_message"}
{"type": "item.updated", "item_id": "uuid", "content": "..."}
{"type": "item.completed", "item_id": "uuid"}
```

### High-Value Item Types for Analysis

**`agent_message`** - What Codex says:
```json
{
  "type": "item.completed",
  "item_type": "agent_message",
  "content": "I've completed the first two tasks..."
}
```

**`reasoning`** - What Codex is thinking:
```json
{
  "type": "item.completed", 
  "item_type": "reasoning",
  "content": "The user wants me to fix the tests. I should first..."
}
```

**`command_execution`** - Shell commands:
```json
{
  "type": "item.completed",
  "item_type": "command_execution",
  "command": "pytest tests/",
  "exit_code": 0,
  "output": "..."
}
```

**`file_change`** - File modifications:
```json
{
  "type": "item.completed",
  "item_type": "file_change",
  "path": "src/module.py",
  "change_type": "modified"
}
```

**`todo_list`** - Task tracking (if emitted):
```json
{
  "type": "item.completed",
  "item_type": "todo_list",
  "items": [
    {"task": "Fix test failures", "status": "completed"},
    {"task": "Update documentation", "status": "in_progress"}
  ]
}
```

### Schema Versioning Notes

⚠️ **Known breaking changes**:
- `item_type` was renamed to `type` in some events
- `assistant_message` renamed to `agent_message`
- Always use defensive parsing with fallbacks

---

## Rollback Plan

If LangChain integration causes issues:
1. Consumer repos: Change `@feature/langchain-analysis` back to `@main`
2. No code changes needed in consumer
3. Feature branch remains available for debugging

---

## Open Questions

1. **~~Codex session logs~~**: Do we need full transcripts, or is the summary sufficient?
   - ✅ **RESOLVED**: Multiple options identified! `--json` mode provides rich JSONL stream.
   - Testing plan includes Phase 0 to evaluate data source options.

2. **`todo_list` event**: Does Codex emit `todo_list` events that map to PR checkboxes?
   - This could be the holy grail for direct checkbox synchronization
   - Need to capture real session to verify event structure

3. **Rate limits**: Does GitHub Models API have rate limits we need to handle?
   - Need to test under load

4. **Checkbox update permissions**: Can workflow token update PR body?
   - Yes, `contents: write` and `pull-requests: write` already granted

5. **JSONL schema stability**: How often do Codex event schemas change?
   - Known issue [#4776](https://github.com/openai/codex/issues/4776) documents field renames
   - Need defensive parsing with fallbacks

---

## Next Steps

### Immediate (Data Source Evaluation)
1. [ ] Modify workflow to capture `--json` output alongside summary
2. [ ] Run Codex manually to capture sample JSONL session
3. [ ] Analyze which event types contain task completion signals
4. [ ] Verify `todo_list` event structure (if present)

### Implementation
5. [ ] Create `feature/langchain-analysis` branch
6. [ ] Implement JSONL parser for Codex events
7. [ ] Implement `llm_provider.py` with fallback chain
8. [ ] Port the three analysis tools with JSONL support
9. [ ] Add workflow integration

### Testing
10. [ ] Set up Portable Alpha for testing
11. [ ] Run Phase 0 data source comparison
12. [ ] Run Phase 1 baseline measurement
13. [ ] Run Phase 2 LangChain measurement
14. [ ] Document results and decide on timing option
