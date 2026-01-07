#!/bin/bash
# Update model list from OpenAI API and GitHub Models API
# Run this periodically to keep model information current
# Requires: OPENAI_API_KEY and/or GITHUB_TOKEN environment variables

set -e

echo "======================================================================"
echo "Model List Update - $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================================================"
echo ""

# Check GitHub Models first (always available in workflows)
if [ -n "$GITHUB_TOKEN" ]; then
    echo "Fetching GitHub Models..."
    curl -s https://models.inference.ai.azure.com/models \
      -H "Authorization: Bearer $GITHUB_TOKEN" | \
    python3 << 'PYEOF'
import json
import sys

try:
    data = json.load(sys.stdin)
    if isinstance(data, list):
        models = sorted([m.get('id', m.get('name', str(m))) for m in data])
        print("GitHub Models API:")
        print("-" * 60)
        # Extract just the model names (after last /)
        gpt_models = []
        llama_models = []
        other_models = []

        for m in models:
            if '/models/' in m:
                parts = m.split('/models/')
                if len(parts) > 1:
                    model_name = parts[1].split('/')[0]
                    if 'gpt' in model_name.lower():
                        gpt_models.append(model_name)
                    elif 'llama' in model_name.lower():
                        llama_models.append(model_name)
                    else:
                        other_models.append(model_name)

        if gpt_models:
            print("GPT Models:")
            for m in sorted(set(gpt_models)):
                print(f"  - {m}")
            print()

        if llama_models:
            print("Meta Llama Models:")
            for m in sorted(set(llama_models)):
                print(f"  - {m}")
            print()

        if other_models:
            print("Other Models:")
            for m in sorted(set(other_models)):
                print(f"  - {m}")
        print()
except Exception as e:
    print(f"Error fetching GitHub Models: {e}", file=sys.stderr)
PYEOF
else
    echo "GitHub Models: GITHUB_TOKEN not set (skipped)"
    echo ""
fi

# Check OpenAI models
if [ -z "$OPENAI_API_KEY" ]; then
    echo "OpenAI Models: OPENAI_API_KEY not set (skipped)"
    echo "Get your API key from: https://platform.openai.com/account/api-keys"
    echo ""
else
    echo "Fetching OpenAI models..."
    curl -s https://api.openai.com/v1/models \
      -H "Authorization: Bearer $OPENAI_API_KEY" | \
    python3 << 'PYEOF'
import json
import sys

try:
    data = json.load(sys.stdin)

    if 'error' in data:
        print(f"Error: {data['error']['message']}", file=sys.stderr)
        sys.exit(1)

    models = sorted([m['id'] for m in data['data']])

    # Categorize models for easier review
    gpt_4_models = [m for m in models if m.startswith('gpt-4') and not m.startswith('gpt-4o')]
    gpt_4o_models = [m for m in models if m.startswith('gpt-4o')]
    gpt_3_models = [m for m in models if m.startswith('gpt-3')]
    o_models = [m for m in models if m.startswith('o1') or m.startswith('o3')]
    other_models = [m for m in models if not any(m.startswith(p) for p in ['gpt-4', 'gpt-3', 'o1', 'o3'])]

    print("OpenAI API:")
    print("-" * 60)

    if o_models:
        print("O-Series (Reasoning Models):")
        for m in o_models:
            print(f"  - {m}")
        print()

    if gpt_4o_models:
        print("GPT-4o (Omni) Series:")
        for m in gpt_4o_models:
            print(f"  - {m}")
        print()

    if gpt_4_models:
        print("GPT-4 Series:")
        for m in gpt_4_models:
            print(f"  - {m}")
        print()

    if gpt_3_models:
        print("GPT-3.5 Series:")
        for m in gpt_3_models:
            print(f"  - {m}")
        print()

    if other_models:
        print("Other Models:")
        for m in other_models:
            print(f"  - {m}")
        print()
except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
PYEOF
fi

echo "======================================================================"
echo ""
echo "Recommendations for workflow configuration:"
echo "  - High Quality: o1, gpt-4o, gpt-4-turbo"
echo "  - Efficient: o3-mini (if available), o1-mini, gpt-4o-mini, gpt-3.5-turbo"
echo ""
echo "Note: Models with suffixes like -YYYY-MM-DD are dated snapshots"
echo "      Base names (e.g., 'gpt-4o') point to the latest stable version"
echo ""
echo "To update workflow configurations:"
echo "  1. Review the model list above"
echo "  2. Update templates/consumer-repo/.github/workflows/agents-verifier.yml"
echo "  3. Update .github/workflows/reusable-agents-verifier.yml if needed"
echo "  4. Commit and push changes"
echo "  5. Sync to consumer repos via sync workflow"
