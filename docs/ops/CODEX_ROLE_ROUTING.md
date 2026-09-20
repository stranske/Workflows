# Codex role routing

The shared coding-worker profiles live in `.github/agents/registry.yml` and
its consumer template copy. Keepalive resolves an active profile before it calls
`reusable-codex-run.yml`; the reusable runner passes the model and reasoning
effort to Codex CLI. An omitted profile selects `codex-default`.

| Work | Active profile | Model | Effort |
| --- | --- | --- | --- |
| Ordinary PR implementation and follow-up | `codex-default` or `codex-implement` | `gpt-5.6-sol` | high |
| Coordination and bounded assessment | `codex-coordinate` | `gpt-5.6-sol` | medium |
| Routine autofix and bounded execution | `codex-routine` or `codex-fast` | `gpt-5.6-terra` | medium |
| Extraction and status summaries | `codex-extract` | `gpt-5.6-luna` | low |
| Difficult judgment and design | `codex-hard` | `gpt-6-astra` | medium |
| Hardest tasks after explicit escalation | `codex-hardest` | `gpt-6-astra` | high |

The root and consumer keepalive workflows accept `execution_profile` on manual
dispatch and honor a profile specified in the PR's keepalive configuration.
Consumer autofix and root autofix callers explicitly select the routine profile;
ordinary PR execution uses the default. The Codex checkbox verifier keeps Astra
at medium effort for consequential acceptance judgments. Auxiliary API evaluators
use `config/llm_slots.json` and `config/model_registry.json`; their benchmark
selection is independent from coding-worker routing. Bundled legacy OpenAI
`gpt-5.2` and `gpt-5.4` slot pins resolve through the reviewed registry
decision; other current pins and caller-supplied slot files remain overrides.

Read-only `reusable-model-profile-trial.yml` arms keep their original trial IDs,
runner pins, and high-effort conditions. They cannot run through ordinary
keepalive. Consumer registry changes are delivered through Maint 68 and the
Maint 71 canary and promotion campaign; the reusable runner takes effect at
`@main` after the source PR merges.
