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

<!--
needs-human:
Label: needs-human
Blocked by workflow protection: reference pack wiring requires edits to protected workflow files in agent-standard.

Workflow: .github/workflows/reusable-codex-run.yml
- Add a preflight step to run `python scripts/reference_packs.py --workspace . --format github-output`.
- Gate on `reference_packs_exists` and fail early when the script exits non-zero (malformed JSON).
- Use `reference_packs_json` / `reference_packs_payload_json` outputs for downstream checkout and markdown generation steps.

What was implemented in code this round:
- Hardened `scripts/reference_packs.py` validation for list format (reject extra top-level keys when `packs` is used).
- Added workflow-ready outputs: `reference_packs_payload_json` and `reference_packs_config_text_b64`.
- Added tests in `tests/scripts/test_reference_packs.py` for:
  - absent config in github-output mode (`reference_packs_exists=false`)
  - payload/config outputs
  - extra-key validation failure in list format.
-->
