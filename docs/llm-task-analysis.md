# LangChain LLM Task Analysis

> **Status**: Production-ready (merged to main)  
> **Added**: January 2026  
> **PRs**: #459 (feature), #461 (PYTHONPATH fix), #462 (logging fix), #463 (permissions)

## Overview

The keepalive automation now uses LLM-powered task completion detection to determine if a Codex session has completed its assigned task. This replaces simple regex-based heuristics with intelligent analysis of session transcripts.

## Architecture

### Provider Chain

The system uses a **fallback chain** of LLM providers:

```
┌─────────────────────┐
│   GitHub Models     │  ← Primary (uses GITHUB_TOKEN)
│   (gpt-4o-mini)     │
└─────────┬───────────┘
          │ on failure
          ▼
┌─────────────────────┐
│      OpenAI         │  ← Secondary (uses OPENAI_API_KEY)
│   (gpt-4o-mini)     │
└─────────┬───────────┘
          │ on failure
          ▼
┌─────────────────────┐
│   Regex Fallback    │  ← Last resort (no API needed)
│   (pattern-based)   │
└─────────────────────┘
```

### Files

| File | Purpose |
|------|---------|
| [tools/llm_provider.py](../tools/llm_provider.py) | LLM provider chain implementation |
| [tools/codex_jsonl_parser.py](../tools/codex_jsonl_parser.py) | Parse Codex session JSONL files |
| [tools/codex_session_analyzer.py](../tools/codex_session_analyzer.py) | Analyze session for task completion |
| [scripts/analyze_codex_session.py](../scripts/analyze_codex_session.py) | CLI script for workflow integration |
| [tools/requirements.txt](../tools/requirements.txt) | Python dependencies (langchain-openai) |

## Workflow Integration

### Reusable Workflow Changes

The `reusable-codex-run.yml` workflow includes:

1. **Sparse checkout** of Workflows repo scripts/tools directories
2. **Install step** for LangChain dependencies
3. **Analyze step** that runs the CLI script
4. **New outputs** for LLM analysis results

```yaml
outputs:
  llm-provider:
    description: 'LLM provider used for analysis'
    value: ${{ jobs.codex.outputs.llm-provider }}
  llm-confidence:
    description: 'Confidence level of LLM analysis'
    value: ${{ jobs.codex.outputs.llm-confidence }}
  session-event-count:
    description: 'Number of events in session'
    value: ${{ jobs.codex.outputs.session-event-count }}
  session-todo-count:
    description: 'Number of todos in session'
    value: ${{ jobs.codex.outputs.session-todo-count }}
```

### PR Comment Display

The keepalive loop script (`keepalive_loop.js`) displays analysis results in PR comments:

```markdown
## 🧠 Task Analysis

| Metric | Value |
|--------|-------|
| Provider | `github-models` |
| Confidence | `high` |
| Events | 42 |
| Todos | 5 |
```

## Configuration

### Required Permissions

The workflow needs `models: read` permission for GitHub Models API:

```yaml
permissions:
  contents: write
  pull-requests: write
  actions: write
  models: read  # For GitHub Models AI inference
```

### Environment Variables

| Variable | Provider | Required |
|----------|----------|----------|
| `GITHUB_TOKEN` | GitHub Models | Auto-provided by Actions |
| `OPENAI_API_KEY` | OpenAI | Optional (fallback) |

### Workflow Input

Consumer workflows can specify which Workflows branch to use:

```yaml
uses: stranske/Workflows/.github/workflows/reusable-codex-run.yml@main
with:
  workflows_ref: 'main'  # Or a specific branch/tag
```

## Usage

### CLI Script

```bash
python scripts/analyze_codex_session.py \
  --jsonl-path /path/to/session.jsonl \
  --output-path /path/to/analysis.json
```

### Output Format

```json
{
  "task_completed": true,
  "confidence": "high",
  "provider": "github-models",
  "reasoning": "Session shows all todos completed with successful verification",
  "event_count": 42,
  "todo_count": 5
}
```

## Provider Details

### GitHub Models (Primary)

- **Model**: `gpt-4o-mini`
- **Endpoint**: `https://models.inference.ai.azure.com`
- **Auth**: `GITHUB_TOKEN` with `models: read` permission
- **Fallback trigger**: 401/403 errors, network failures

### OpenAI (Secondary)

- **Model**: `gpt-4o-mini`
- **Auth**: `OPENAI_API_KEY` environment variable
- **Fallback trigger**: API errors, missing key

### Regex Fallback (Last Resort)

Pattern-based detection looking for:
- "task completed" / "task complete"
- "all todos completed"
- "successfully implemented"
- Exit code 0 with positive indicators

## Consumer Repo Updates

Consumer repositories need to sync their workflow templates to get:

1. Updated `keepalive_loop.js` with Task Analysis section
2. Updated workflow that passes LLM outputs

**Sync PR**: Check for open sync PRs in consumer repos (e.g., `sync/workflows-*` branches)

## Troubleshooting

### GitHub Models 401 Error

```
The 'models' permission is required to access this endpoint
```

**Fix**: Add `models: read` to workflow permissions (PR #463)

### Import Errors

```
ModuleNotFoundError: No module named 'tools'
```

**Fix**: Ensure `PYTHONPATH` includes `.workflows-lib` directory

### JSON Parse Errors

If analysis output contains logging messages:

**Fix**: Logging now goes to stderr (PR #462)

## Development History

| PR | Description |
|----|-------------|
| #459 | Initial LangChain feature implementation |
| #461 | Fix PYTHONPATH for tools imports |
| #462 | Redirect logging to stderr |
| #463 | Add models:read permission |

## Testing

Test PR in Manager-Database: #136 (`test/langchain-keepalive` branch)

To test locally:

```bash
# Install dependencies
pip install -r tools/requirements.txt

# Run analysis
export GITHUB_TOKEN="your-token"
python scripts/analyze_codex_session.py \
  --jsonl-path test-session.jsonl \
  --output-path analysis.json
```
