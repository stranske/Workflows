**Purpose**
This folder contains YAML snippets that must be manually applied to protected GitHub Actions workflow files. The changes are not applied in this PR because `.github/workflows/**` is protected under the `agent-standard` permission model.

**Apply Instructions**
1. Open `.github/workflows/agents-auto-pilot.yml`.
2. Update the existing `Set up Python` step to include `id: setup-python` (this is required for the cache key).
3. Insert the cache step from `docs/workflow-updates/agents-auto-pilot-changes.yml` immediately after the updated `Set up Python` step.
4. Replace the existing `Install Python dependencies` step with the install step from `docs/workflow-updates/agents-auto-pilot-changes.yml`.

5. Open `.github/workflows/agents-issue-optimizer.yml`.
6. Confirm the `Install dependencies` step uses `python -m pip install -r tools/requirements-llm.txt` and does not install unpinned `langchain` packages.

7. Open `.github/workflows/reusable-agents-verifier.yml`.
8. Update the existing `Setup Python for LLM evaluation` step to include `id: setup-python-evaluate`.
9. Insert the evaluate-mode cache step from `docs/workflow-updates/reusable-agents-verifier-changes.yml` immediately after that setup step.
10. Replace the existing `Install LLM evaluation dependencies` step with the evaluate install step from `docs/workflow-updates/reusable-agents-verifier-changes.yml`.

11. Update the existing `Setup Python for comparison` step to include `id: setup-python-compare`.
12. Insert the compare-mode cache step from `docs/workflow-updates/reusable-agents-verifier-changes.yml` immediately after that setup step.
13. Replace the existing `Install comparison dependencies` step with the compare install step from `docs/workflow-updates/reusable-agents-verifier-changes.yml`.

**Verification**
1. Confirm `.github/workflows/agents-auto-pilot.yml` contains `python -m pip install -r tools/requirements-llm.txt` and no unpinned `langchain` install commands.
2. Confirm `.github/workflows/agents-issue-optimizer.yml` contains `python -m pip install -r tools/requirements-llm.txt` and no unpinned `langchain` install commands.
3. Confirm `.github/workflows/reusable-agents-verifier.yml` contains `pip install -r .workflows-lib/tools/requirements-llm.txt` in both evaluate and compare paths.
4. Confirm both cached workflows include `actions/cache@v4` steps with keys that include `python-version` and the relevant `hashFiles(...)` call.

**Notes**
The cache key format uses `steps.<setup-step-id>.outputs.python-version`, so the `id` additions are required for the cache key to include the Python version.
