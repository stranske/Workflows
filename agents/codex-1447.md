<!--
needs-human:
Label: needs-human
Workflow updates required in .github/workflows/agents-auto-pilot.yml and .github/workflows/reusable-agents-verifier.yml. Add pinned installs (`pip install -r tools/requirements-llm.txt` and `pip install -r .workflows-lib/tools/requirements-llm.txt` for evaluate/compare), add actions/cache@v5 pip cache keyed by Python version + requirements hash (`${{ hashFiles('tools/requirements-llm.txt') }}` and `${{ hashFiles('.workflows-lib/tools/requirements-llm.txt') }}`), and remove any floating `pip install langchain*` lines. Workflow edits require agent-high-privilege.
-->
