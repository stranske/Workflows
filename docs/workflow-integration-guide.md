# Workflow Integration Guide

Use the checked-in workflows to find the current Python dependency and cache
steps. The [Workflow Guide](WORKFLOW_GUIDE.md) covers the triggers and operator
entry points for these workflows.

| Workflow | Current dependency setup |
| --- | --- |
| [Auto Pilot](../.github/workflows/agents-auto-pilot.yml) and [consumer template](../templates/consumer-repo/.github/workflows/agents-auto-pilot.yml) | `Set up Python`, `Cache pip (LLM requirements)` and `Install Python dependencies`. The cache key uses the setup step's Python version and hashes `tools/requirements-llm.txt`. |
| [Reusable verifier](../.github/workflows/reusable-agents-verifier.yml), called by the [consumer verifier](../templates/consumer-repo/.github/workflows/agents-verifier.yml) | The evaluate and compare branches each have their own Python setup, cache and install steps. Their keys use the corresponding setup step and `.workflows-lib/tools/requirements-llm.txt`. |
| [Verify to New PR](../.github/workflows/agents-verify-to-new-pr.yml) and [consumer template](../templates/consumer-repo/.github/workflows/agents-verify-to-new-pr.yml) | `Install dependencies` installs `langchain`, `langchain-openai`, `langchain-anthropic` and `requests` after the workflow checks out Workflows with `tools` in its sparse checkout. |

## Pending dependency proposal

The [Verify to New PR install snippet](workflow-snippets/agents-verify-to-new-pr-install.yml)
proposes using the [seven pinned dependencies](../tools/requirements-llm.txt)
for the four packages installed directly today. Adopting those pins introduces
three additional direct dependencies. It requires separate validation on the
follow-up workflow.

## Deterministic verdict extraction

Verify to New PR already runs `Extract verdict via verdict_policy` with step
ID `extract-verdict`. It reads the generated `verification_data.txt` using the
[verdict reader](../scripts/langchain/verdict_extract.py).

```bash
python -m scripts.langchain.verdict_extract \
  --summary-path verification_data.txt \
  --policy worst \
  --emit github
```

The `github` emitter writes `verdict`, `needs_human`, `needs_human_reason`,
`policy`, `verdict_kind`, `selected_provider`, `selected_model`,
`selected_confidence`, `split_verdict`, `concerns_confidence` and
`verdict_metadata` to `GITHUB_OUTPUT`. The workflow consumes the verdict and
needs-human outputs through `steps.extract-verdict.outputs`.

## Historical snippets

The February examples remain available as reference material.

- [Auto Pilot install](workflow-snippets/agents-auto-pilot-install.yml)
- [Reusable verifier installs](workflow-snippets/reusable-agents-verifier-install.yml)
- [Generic pip cache](workflow-snippets/pip-cache-step.yml)
- [Optional pip freeze logging](workflow-snippets/pip-freeze-step.yml)
