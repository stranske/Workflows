### Keepalive: ON
<!-- meta:issue:4363 -->

### Source Issue #4363: Track GitHub Models fallback retirement and consumer migration

Closes #4363

Head: codex/issue-4363

Opened by opener-core so codex engages (invite-mode intake).

<!-- pr-preamble:start -->
<!-- meta:issue:4363 -->
> **Source:** Issue #4363

Closes #4363

<!-- pr-preamble:end -->

<!-- auto-status-summary:start -->
## Automated Status Summary
#### Scope
GitHub Models is no longer used as a fallback provider per owner decision 2026-10-31. Tool execution falls back between OpenAI and Anthropic only, with Muse preserved as the capacity backup in slot 3. Existing consumer repositories retaining legacy slot definitions must be handled gracefully without breaking freshness validation or runtime execution.

<!-- Updated WORKFLOW_OUTPUTS.md context:start -->
## Context for Agent

### Related Issues/PRs
- [stranske/Workflows#4362](https://github.com/stranske/Workflows/issues/4362)
- [#4362](https://github.com/stranske/Workflows/issues/4362)
<!-- Updated WORKFLOW_OUTPUTS.md context:end -->

#### Tasks
- [x] Update `config/llm_slots.json` and `templates/consumer-repo/config/llm_slots.json` to remove the slot3 github-models entry while preserving slot 3 Muse capacity backup.
- [x] Update `config/model_registry.json` and `templates/consumer-repo/config/model_registry.json` to move the provisional verifier-balanced github-models selection into `selection_history` with `superseded_by: "retired"`.
- [x] Update `tools/llm_registry.py` function `default_slots` to auto-select only between OpenAI and Anthropic, and function `load_slot_config` to skip retired selections at runtime.
- [x] Update `tools/check_model_registry_freshness.py` to classify create-only consumer slots referencing retired selections as advisory `retired_slot` findings instead of blocking `missing_selection`.
- [x] Update `scripts/langchain/task_decomposer.py` to remove `GITHUB_TOKEN`-only fallback branches targeting GitHub Models.
- [x] Add test cases in `tests/tools/test_langchain_client.py` and `tests/test_check_model_registry_freshness.py` asserting no client is created from `GITHUB_TOKEN` alone and stale consumer slots for retired models never instantiate clients.

#### Acceptance criteria
- [x] Run `python3 -m pytest -q tests/tools/test_langchain_client.py tests/test_check_model_registry_freshness.py` and confirm all tests pass.
- [x] Run `python3 tools/check_model_registry_freshness.py` and confirm the script exits with status code 0.
- [x] In `config/llm_slots.json`, verify `capacity_backup.provider` remains `muse-api` and `capacity_backup.slot` is `slot3`.

<!-- auto-status-summary:end -->

### Validation and task reconciliation
Reviewed commits `239604bb` and `05ed0d21`: they add regression tests; the requested configuration and runtime changes are already present in the base. Verified all six tasks against the current implementation. The required two-file pytest suite passes (207 tests). The extended suite including registry selection, retirement configuration, and task decomposer tests passes (350 tests). Four new cases verify that direct defaults and an absent default slot file both exclude GitHub Models even when a legacy registry still has an active GitHub Models selection, with or without a legacy github_default_model argument. `python3 tools/check_model_registry_freshness.py` exits 0 with 0 blocking findings and one existing overdue-review advisory. Both source and template retain the enabled `muse-api` capacity backup in `slot3`.

Validation commands:

```text
python3 -m pytest -q tests/tools/test_langchain_client.py tests/test_check_model_registry_freshness.py
207 passed

python3 -m pytest -q tests/tools/test_llm_registry_selection.py tests/tools/test_langchain_client.py tests/test_check_model_registry_freshness.py tests/test_model_registry_retirement.py tests/scripts/test_task_decomposer.py -m 'not slow'
350 passed

python3 tools/check_model_registry_freshness.py
0 blocking, 1 advisory; exit 0

black --check --line-length 100 tests/tools/test_llm_registry_selection.py
1 file would be left unchanged
```

Local handoff limitations:

- This is a proposed replacement PR body. The GitHub update was blocked with
  `MCP tool call requires approval, but approval policy is never`; the remote
  checkboxes were not changed.
- The required repository-wide command
  `black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .`
  failed during Python 3.14 worker startup with `PermissionError: Operation not permitted`
  when its forkserver tried to bind a socket. A retry with `BLACK_NUM_WORKERS=1`
  produced no result and was interrupted. The edited file was formatted and passes
  its individual check, but the repository-wide formatting gate is unverified.
- Staging failed because `.git` is read-only and `git add` cannot create
  `.git/index.lock`. No commit or push was made. The runner must rerun the full
  formatting gate and commit the test and this reconciliation artifact.
- PR #4525 was verified open and ready for review (`draft=false`) after validation.
