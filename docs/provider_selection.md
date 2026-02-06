# Provider Selection

This repository uses a shared LangChain client helper in tools/langchain_client.py.
Provider selection follows these rules:

1. If force_openai=True, the helper prefers OpenAI, but can fall back to GitHub
   Models when OPENAI_API_KEY is missing and GITHUB_TOKEN is available. If no
   fallback is possible, a controlled exception is raised.
2. If provider is set (argument or LANGCHAIN_PROVIDER), it must be one of:
   - github-models
   - openai
   Invalid values trigger a warning and fall back to auto-selection.
3. Auto-selection prefers GitHub Models when GITHUB_TOKEN is available, then
   falls back to OpenAI when OPENAI_API_KEY is available.

Environment overrides:

- LANGCHAIN_PROVIDER: force provider selection (github-models or openai).
- LANGCHAIN_MODEL: override the default model name.
- LANGCHAIN_TIMEOUT: override request timeout in seconds.
- LANGCHAIN_MAX_RETRIES: override retry count.

Timeout and retry overrides are read at call time so changes in the environment
are honored per invocation.
