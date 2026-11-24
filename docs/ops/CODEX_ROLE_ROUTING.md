# Codex role routing

The active coding-worker profiles are declared in the [agent registry](../../.github/agents/registry.yml)
and its [consumer template copy](../../templates/consumer-repo/.github/agents/registry.yml).
Keepalive resolves a profile before it calls the [reusable Codex runner](../../.github/workflows/reusable-codex-run.yml).
The runner uses the [shared model table](../../.github/agents/model-table.json)
to choose the model and reasoning effort it passes to Codex CLI. An omitted
profile selects `codex-default`.

| Work | Active profile | Work kind | Effort |
| --- | --- | --- | --- |
| Ordinary PR implementation and follow-up | `codex-default` or `codex-implement` | `implement` | high |
| Coordination and bounded assessment | `codex-coordinate` | `coordinate` | medium |
| Routine autofix and bounded execution | `codex-routine` or `codex-fast` | `routine` | medium |
| Extraction and status summaries | `codex-extract` | `extract` | low |
| Difficult judgment and design | `codex-hard` | `hard` | medium |
| Hardest tasks after explicit escalation | `codex-hardest` | `hardest` | high |

With the repository's Python environment active, run the [resolver](../../scripts/agent_model_table.py)
from the Workflows root to see the current hosted choice for one of the active
profiles listed above. Ordinary keepalive admits only active profiles from its
registry.

```sh
python3 scripts/agent_model_table.py resolve --agent codex --surface hosted \
  --execution-profile codex-coordinate
```

The output includes the model, reasoning effort and applicable fallback. Use
`--surface local` for the local Orchestrator choice represented by this checkout's
table. The [model-table check](../../scripts/check_model_tables.py) compares
Workflows with the Orchestrator copy.

The [root keepalive workflow](../../.github/workflows/agents-keepalive-loop.yml)
and [consumer Gate follow-ups workflow](../../templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml)
accept `execution_profile` on manual dispatch. For Codex execution, keepalive
uses the profile from the PR's keepalive configuration first, then the manual
dispatch input, then `codex-default`. Consumer autofix and [root autofix](../../.github/workflows/agents-autofix-loop.yml)
callers explicitly select the routine profile. Ordinary PR execution uses the default. The
[Codex checkbox verifier](../../.github/workflows/reusable-agents-verifier.yml)
uses Astra at medium effort for consequential acceptance judgments. Auxiliary API
evaluators use [LLM slots](../../config/llm_slots.json) and the
[model registry](../../config/model_registry.json) for independent benchmark
selection. Bundled legacy OpenAI `gpt-5.2` and `gpt-5.4` slot pins resolve
through the reviewed registry decision. Other current pins and caller-supplied
slot files remain overrides.

The [read-only profile trials](../../.github/workflows/reusable-model-profile-trial.yml)
keep their original trial IDs, runner pins, and high-effort conditions. Use the
trial workflow for those profiles. [Maint 68](../../.github/workflows/maint-68-sync-consumer-repos.yml)
and [Maint 71](../../.github/workflows/maint-71-merge-sync-prs.yml) deliver
consumer registry changes through canary and promotion. The reusable runner
takes effect at `@main` after the source PR merges.
