# Model Management Guide

## Quick Update Process

To see the models available to an OpenAI API key, set `OPENAI_API_KEY` in your shell and run this read-only query. Keep the result local if it contains account-specific model IDs.

```bash
set -o pipefail
curl --fail --silent --show-error https://api.openai.com/v1/models \
  -H "Authorization: Bearer ${OPENAI_API_KEY:?Set OPENAI_API_KEY first}" |
  jq -r '.data | map(.id) | sort[]'
```

In a consumer repository, open **Actions → List LLM Models**, select the default branch and choose **openai**. The workflow documents what it can publish for public and private repositories. The **github-models** catalog option is retired. [Consumer workflow](../templates/consumer-repo/.github/workflows/list-llm-models.yml)

## Scheduled Updates

Maint 77 checks the registry and reports catalog changes weekly. To run the same discovery tool locally for OpenAI, use the repository's Python environment from the checkout root.

```bash
python tools/discover_model_catalog.py --provider openai
```

Read the provider's `status` in the JSON report. It gives the observed count and changes against the recorded baseline when the provider responds. An unavailable credential or service produces `skipped` with the reason. Detected drift returns exit code 1. [Catalog discovery policy](MODEL_SELECTION_POLICY.md#catalog-discovery) · [Maint 77](../.github/workflows/maint-77-model-registry-freshness.yml)

## Testing New Models

To inspect the chosen profiles, their review dates and the evidence behind them, read the selections in the registry.

```bash
jq .selections config/model_registry.json
```

Use the selection policy to compare a candidate against the incumbent on the recorded workload and to prepare a reviewed promotion or rollback. The slot configuration records the runtime assignments. [Selection policy](MODEL_SELECTION_POLICY.md) · [Model registry](../config/model_registry.json) · [Runtime slots](../config/llm_slots.json)
