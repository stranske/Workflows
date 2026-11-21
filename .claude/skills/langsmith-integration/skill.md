# Tracing Workflows LLM calls

Workflows uses LangChain runnables to attach GitHub context to model calls and return trace references. The issue formatter is a working example. [Issue formatter](../../../scripts/langchain/issue_formatter.py) · [Tracing helper](../../../scripts/langchain/trace_utils.py)

## Instrument a call

Pass the workflow secret `LANGSMITH_API_KEY` to the step that runs the model. A reusable workflow caller must pass or inherit that secret. With a key present, the shared provider defaults `LANGCHAIN_PROJECT` to `workflows-agents` and `LANGCHAIN_TRACING_V2` to `true`. An explicit `LANGCHAIN_TRACING_V2=false` disables tracing. [Verifier workflow](../../../.github/workflows/reusable-agents-verifier.yml) · [Provider configuration](../../../tools/llm_provider.py)

In the issue formatter, `chain` is the existing prompt and model runnable, and `issue_body` is its input. Wrap that call once to attach the operation, repository and run metadata.

```python
from scripts.langchain.trace_utils import invoke_with_trace

response, trace = invoke_with_trace(
    chain,
    {"issue_body": issue_body},
    operation="issue_formatter",
)
```

Use `response` for the model result. Where a result record accepts trace references, `trace.as_dict()` supplies available `langsmith_trace_id` and `langsmith_trace_url` fields. A response can succeed with no trace reference. The helper logs the URL when available.

## Verify the integration

From the repository root, run the helper and opt-out tests with the repository’s Python environment.

```sh
python -m pytest -q tests/scripts/test_trace_utils.py tests/tools/test_llm_provider_tracing_opt_out.py
```

On a normal keyed run, open the trace reference and match its operation, repository and GitHub run ID in the configured LangSmith project. If the response lacks a reference or the link does not resolve, search that project using the same metadata. The provider can fall back to a model message ID, so a generated URL alone cannot confirm a cloud trace. The fleet dashboard separately validates exported records. Its observability contract describes how to distinguish cloud trace freshness, artifact validity and Orchestrator import. [Fleet observability contract](../../../docs/contracts/langsmith-observability-contract.md) · [Export record format](../../../docs/contracts/langsmith-fleet-v1.md)
