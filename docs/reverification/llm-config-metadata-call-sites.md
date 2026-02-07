# LLM Config/Metadata Propagation Call Sites

This document enumerates the LLM invocation call sites that pass config/metadata
payloads into LangChain clients so tests can verify propagation behavior.

## Call Site Inventory

- `scripts/langchain/pr_verifier.py`
  - `ComparisonRunner.run_single()`
    - Calls `_invoke_llm(..., operation="evaluate_pr_compare", context=...)`.
  - `evaluate_pr()`
    - Calls `_invoke_llm(..., operation="evaluate_pr", context=...)` for the primary
      evaluation path.

- `scripts/langchain/followup_issue_generator.py`
  - `_generate_with_llm()`
    - Calls `_invoke_llm(..., operation="analyze_verification", pr_number=..., issue_number=...)`.
    - Calls `_invoke_llm(..., operation="generate_tasks", pr_number=..., issue_number=...)`.
    - Calls `_invoke_llm(..., operation="generate_acceptance_criteria", pr_number=..., issue_number=...)`.
    - Calls `_invoke_llm(..., operation="format_followup_issue", pr_number=..., issue_number=...)`.

## Notes

- The shared config/metadata payload is assembled by `_build_llm_config()` in each module
  and passed via the `config=` keyword in the `client.invoke(...)` call.
- Tests should assert the exact metadata and tags passed to each invocation above.
