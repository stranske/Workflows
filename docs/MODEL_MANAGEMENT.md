# Model Management Guide

## Keeping Model Lists Current

The workflows support various LLM models from different providers. This guide explains how to keep the model lists up-to-date.

## Quick Update Process

```bash
# Set your OpenAI API key
export OPENAI_API_KEY="sk-..."

# Run the update script
./scripts/update_model_list.sh
```

This will fetch the current list of available models from OpenAI's API and display them categorized by series.

## Manual API Query

You can also query the API directly:

```bash
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY" | jq '.data[].id' | sort
```

## Model Selection Guidelines

### GitHub Models (no extra API key required)
- **gpt-4o**: Default for verify:evaluate - best available on GitHub Models
- **Mistral-large-2407**: Mistral flagship, used for cross-family comparison
- **Meta-Llama-3.1-405B-Instruct**: Meta's largest model

### OpenAI Models (requires OPENAI_API_KEY)
- **o1 / o1-preview**: Reasoning models - best for critical evaluation
- **gpt-5.2**: High-quality strict evaluation

### Efficient Models (for rapid iteration)
- **gpt-4o-mini**: Fast, cost-effective (but too lenient for verification)
- **Mistral-Nemo**: Smaller Mistral model

### Verification Mode Defaults
- **verify:evaluate**: gpt-4o (best GitHub Models option, no extra key needed)
- **verify:compare**: gpt-5.2 (OpenAI) + Mistral-large-2407 (GitHub Models)

Note: gpt-4o-mini was found to be too lenient, passing obvious deficiencies.
verify:compare requires OPENAI_API_KEY for gpt-5.2 but provides stricter
cross-provider evaluation with diverse perspectives.

### GitHub Models vs OpenAI

**GitHub Models API** (`https://models.inference.ai.azure.com`):
- Uses GITHUB_TOKEN (no additional API key needed)
- Provides access to various models including Meta-Llama
- May have different model availability than OpenAI

**OpenAI API** (`https://api.openai.com`):
- Requires OPENAI_API_KEY
- Direct access to all OpenAI models
- Generally has latest models first

## Updating Workflow Configurations

After checking current models, update these files:

### 1. Consumer Template Workflow
**File**: `templates/consumer-repo/.github/workflows/agents-verifier.yml`

Update the model descriptions:
```yaml
model:
  description: >-
    GitHub Models: [list here] | OpenAI: [list here]
```

Update default values for compare mode (lines ~155-156):
```javascript
core.setOutput('model', 'gpt-4o');  // High quality model
core.setOutput('model2', 'o1');     // Different high quality model
```

### 2. Reusable Workflow (if needed)
**File**: `.github/workflows/reusable-agents-verifier.yml`

Update input descriptions if model lists change significantly.

### 3. Sync Changes
After updating templates:
```bash
git add templates/consumer-repo/.github/workflows/agents-verifier.yml
git commit -m "Update model lists to current OpenAI offerings"
git push
```

The sync workflow will automatically propagate changes to consumer repos.

## Testing New Models

Before setting as defaults, test new models:

```bash
# Test with pr_verifier locally
python scripts/langchain/pr_verifier.py \
  --repo owner/repo \
  --pr 123 \
  --mode evaluate \
  --model "new-model-name" \
  --json
```

Or trigger workflow manually with `workflow_dispatch` and specify the model.

## Model Naming Notes

- **Base names** (e.g., `gpt-4o`) point to latest stable version
- **Dated versions** (e.g., `gpt-4o-2024-08-06`) are frozen snapshots
- Use base names in workflows for automatic updates
- Use dated versions when reproducibility is critical

## Resources

- **OpenAI Models Docs**: https://platform.openai.com/docs/models
- **OpenAI API Reference**: https://platform.openai.com/docs/api-reference/models
- **GitHub Models**: GitHub.com → Settings → GitHub Models (for available models)

## Scheduled Updates

Recommend checking for model updates:
- Monthly for production stability
- Weekly if using cutting-edge features
- After OpenAI announces new releases

Run `./scripts/update_model_list.sh` to check current availability.
