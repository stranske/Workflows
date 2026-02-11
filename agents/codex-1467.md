<!--
needs-human:
Label: needs-human
Blocked by workflow protection: fix cache key patterns in protected workflow files to satisfy CI test expectations.

Workflow: .github/workflows/agents-auto-pilot.yml
- Ensure there is an `actions/cache@v4` step for pip cache with a key that includes both `python-version` and `${{ hashFiles('tools/requirements-llm.txt') }}`.
- Keep install source pinned to `pip install -r tools/requirements-llm.txt` (no floating `pip install langchain*`).

Workflow: .github/workflows/reusable-agents-verifier.yml
- Ensure there is an `actions/cache@v4` step for pip cache with a key that includes both `python-version` and `${{ hashFiles('.workflows-lib/tools/requirements-llm.txt') }}`.
- Keep install source pinned to `.workflows-lib/tools/requirements-llm.txt` for verifier LLM dependencies.

Reproduction:
- `pytest -q --maxfail=20`
- Failing tests:
  - `tests/workflows/test_workflow_llm_installs.py::test_agents_auto_pilot_pip_cache_is_configured`
  - `tests/workflows/test_workflow_llm_installs.py::test_reusable_agents_verifier_pip_cache_is_configured`
-->
