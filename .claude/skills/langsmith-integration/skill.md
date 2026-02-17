# LangSmith Integration Skill

## Purpose

This skill documents the process for integrating LangSmith tracing into workflow LLM calls. Use this when adding observability to LLM-powered workflows.

## When to Use

- Adding LangSmith tracing to a new LLM-powered workflow
- Debugging LLM call issues in existing workflows
- Reviewing LangSmith integration completeness
- Understanding trace ID propagation patterns

## Architecture Overview

LangSmith integration follows a layered approach:

```
Workflow YAML (agents-*.yml, reusable-*.yml)
    ↓ sets environment variables
Python Script (.github/scripts/*.py, tools/*.py)
    ↓ uses LLMProvider wrapper
LLMProvider (tools/llm_provider.py)
    ↓ configures LangSmith client
LangSmith API
    ↓ stores traces
LangSmith UI (https://smith.langchain.com)
```

## Integration Checklist

### 1. Workflow Configuration

Every workflow using LLMs must set these environment variables:

```yaml
env:
  # Required for all LLM calls
  LANGCHAIN_TRACING_V2: "true"
  LANGCHAIN_PROJECT: "workflow-project-name"
  LANGCHAIN_API_KEY: ${{ secrets.LANGCHAIN_API_KEY }}

  # GitHub context (for trace metadata)
  GITHUB_REPOSITORY: ${{ github.repository }}
  GITHUB_RUN_ID: ${{ github.run_id }}
  GITHUB_SHA: ${{ github.sha }}
```

**Project naming convention:**
- Use descriptive, kebab-case names
- Include workflow purpose: `autopilot-issue-formatter`, `verifier-evaluate`
- Group related workflows: `verifier-*`, `autopilot-*`

### 2. Python Script Integration

Scripts must use `LLMProvider` instead of direct provider calls:

```python
from tools.llm_provider import LLMProvider

# Initialize provider
provider = LLMProvider(
    provider_name="openai",  # or "anthropic"
    model="gpt-4o",
    temperature=0.7
)

# Make LLM call (automatically traced)
response = provider.invoke(messages)

# Extract trace ID for logging/output
trace_id = provider.get_trace_id(response)
print(f"LangSmith trace: https://smith.langchain.com/o/.../p/.../r/{trace_id}")
```

**Benefits:**
- Automatic trace capture
- Consistent error handling
- Standardized metadata injection
- Trace ID extraction

### 3. Trace Metadata

LLMProvider automatically adds:
- GitHub run context (repo, run_id, sha, workflow)
- Timestamps
- Model configuration
- Token usage (when available)

### 4. Verification

After integration, verify traces appear:

1. **Trigger workflow** with LLM call
2. **Check workflow logs** for trace URLs
3. **Visit LangSmith UI** to confirm trace exists
4. **Verify metadata** includes GitHub context

## Common Patterns

### Pattern 1: Issue Formatting/Processing

```yaml
# agents-auto-pilot.yml or similar
jobs:
  format:
    env:
      LANGCHAIN_TRACING_V2: "true"
      LANGCHAIN_PROJECT: "autopilot-issue-formatter"
      LANGCHAIN_API_KEY: ${{ secrets.LANGCHAIN_API_KEY }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt
      - run: python .github/scripts/issue_formatter.py ${{ github.event.issue.number }}
```

### Pattern 2: Reusable Workflow with LLM

```yaml
# reusable-verifier.yml
on:
  workflow_call:
    secrets:
      langchain_api_key:
        required: true

jobs:
  verify:
    env:
      LANGCHAIN_TRACING_V2: "true"
      LANGCHAIN_PROJECT: "verifier-evaluate"
      LANGCHAIN_API_KEY: ${{ secrets.langchain_api_key }}
```

### Pattern 3: Multi-Step Pipeline

```yaml
# Each step gets its own project for trace organization
jobs:
  step1:
    env:
      LANGCHAIN_PROJECT: "pipeline-step1-analyze"
  step2:
    env:
      LANGCHAIN_PROJECT: "pipeline-step2-generate"
  step3:
    env:
      LANGCHAIN_PROJECT: "pipeline-step3-validate"
```

## Troubleshooting

### Traces Not Appearing

**Check workflow logs for:**
```
LangSmith tracing enabled
Project: project-name
Trace URL: https://smith.langchain.com/...
```

**Common causes:**
- `LANGCHAIN_API_KEY` not set or incorrect
- `LANGCHAIN_TRACING_V2` not set to `"true"` (must be string)
- Network issues (LangSmith API unreachable from runner)

### Missing Trace IDs

**Symptom:** Workflow completes but no trace URL in logs

**Diagnosis:**
1. Check `provider.get_trace_id(response)` is called
2. Verify response object has trace metadata
3. Check provider compatibility (OpenAI/Anthropic tested)

**Fix:** Ensure script uses `LLMProvider.invoke()` not direct SDK calls

### Metadata Not Attached

**Check:**
- Environment variables (GITHUB_*) are set in workflow
- LLMProvider initialization includes metadata parameter
- LangSmith project permissions allow metadata writes

## Testing Integration

### Local Testing

```bash
# Set up environment
export LANGCHAIN_TRACING_V2="true"
export LANGCHAIN_PROJECT="local-test"
export LANGCHAIN_API_KEY="lsv2_..."
export GITHUB_REPOSITORY="test/repo"
export GITHUB_RUN_ID="123"

# Run script
python .github/scripts/your_script.py

# Check for trace URL in output
```

### CI Testing

1. Create test workflow that uses LLM
2. Trigger manually via `workflow_dispatch`
3. Verify trace appears in LangSmith
4. Check metadata includes correct GitHub context

## Migration Strategy

For existing LLM-using workflows:

1. **Audit:** Find all direct OpenAI/Anthropic SDK calls
   ```bash
   grep -r "OpenAI()" .github/scripts/ tools/
   grep -r "ChatAnthropic()" .github/scripts/ tools/
   ```

2. **Prioritize:** Start with high-frequency workflows
   - agents-auto-pilot.yml (format, optimize steps)
   - agents-verifier.yml (evaluate, compare modes)
   - agents-verify-to-new-pr.yml (analysis pipeline)

3. **Convert:** Replace direct SDK usage with LLMProvider

4. **Test:** Run workflow and verify traces

5. **Document:** Add trace URL to workflow output/summary

## Files Reference

| File | Purpose |
|------|---------|
| `tools/llm_provider.py` | LLMProvider wrapper class |
| `tools/requirements.txt` | LangChain/LangSmith dependencies |
| `.github/workflows/agents-auto-pilot.yml` | Example integration |
| `.github/workflows/reusable-verifier.yml` | Example reusable workflow |
| `.github/scripts/issue_formatter.py` | Example Python script |

## Best Practices

1. **One project per workflow step** - Easier trace filtering
2. **Include trace URLs in summaries** - Quick debugging access
3. **Use metadata liberally** - GitHub context invaluable for correlation
4. **Test locally first** - Faster iteration than CI loops
5. **Monitor costs** - LangSmith has usage limits on free tier

## Future Enhancements

- [ ] Automatic trace URL injection into PR comments
- [ ] Trace-to-GitHub-Run linking in LangSmith UI
- [ ] Cost tracking dashboard from LangSmith data
- [ ] Trace replay for debugging failed runs
- [ ] Custom metadata for domain-specific tracking

## Related Documentation

- [LangSmith Docs](https://docs.smith.langchain.com/)
- [LangChain Tracing](https://python.langchain.com/docs/langsmith/tracing)
- [tools/llm_provider.py](../../tools/llm_provider.py) - Implementation details
- [CLAUDE.md](../../CLAUDE.md) - Repository context

---

**Last Updated:** 2026-02-17
**Maintainer:** Workflows team
**Status:** Active - integration in progress
