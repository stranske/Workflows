# Workloop State

## 2026-05-13T22:31:06Z

- Lane: opener / codex
- Repo: stranske/Workflows
- Issue: #2085 Align workflow source docs with Gate autofix and verifier defaults
- PR: #2092 https://github.com/stranske/Workflows/pull/2092
- Branch: codex/issue-2085-workflow-source-docs
- Status: PR opened and same-lane CI recovery applied locally; push pending
- Changes:
  - Updated README verify:compare model pair to `gpt-5.4 + claude-sonnet-4-6`.
  - Updated docs/ci/WORKFLOWS.md target-layout autofix path to name Gate `autofix_gate_failure` dispatch through `agents-autofix-dispatcher.yml` and `agents-autofix-loop.yml`.
  - Added tests/docs/test_workflow_source_docs.py to assert README model docs match `tools.langchain_client._default_slots()` and that WORKFLOWS.md names the live Gate autofix dispatch path.
- Validation:
  - `python -m pytest tests/docs/test_workflow_source_docs.py tests/tools/test_langchain_client.py tests/workflows/test_workflow_autofix_guard.py -q` -> 58 passed.
  - `rg "gpt-5\.2" README.md` -> no matches.
  - Initial `bash scripts/dev_check.sh` under Python 3.12 venv with a Bash 3 `mapfile` compatibility shim reached formatting, then failed on Black drift in `scripts/repo_review_backlog_scan.py`, `scripts/repo_review_notify.py`, and `scripts/repo_review_round2_runner.py`.
  - Same-lane CI recovery: applied `black --line-length 100` to the three script files named by Gate plus the new docs test.
  - `black --check --line-length 100 .` -> passed.
  - `python -m compileall scripts/ -q` -> passed.
  - Full `bash scripts/dev_check.sh` under Python 3.12 venv with Bash 3 `mapfile` compatibility shim -> passed.
- Cap state before selection: raw opener cap below limit at 4/5. Existing opener-owned PRs: Pension-Data #424 runner-failed, Pension-Data #427 runner-failed, Portable-Alpha-Extension-Model #1787 runner-failed, Trend_Model_Project #5293 draining.
- Post-open cap state: raw cap reached at 5/5. Workflows #2092 is draining with active Gate evidence. Existing stuck cap PRs remain Pension-Data #424 runner-failed, Pension-Data #427 runner-failed, and Portable-Alpha-Extension-Model #1787 runner-failed; repair helper reported all runner-failed PRs as not repairable by opener.
- Next action: push recovery commit, re-check PR routing/checks, emit `pr_opened`.
