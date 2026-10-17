## Summary

Latest local validation: **239 related tests passed; 95.47% target coverage**. This iteration adds a CLI regression for bounded diagnostics and complete generated tasks. Production source is unchanged.

- add focused regression coverage for mixed verifier input, JSON/Markdown parsing, advisory notes, disposition fallback, and CLI file/stdin paths
- retain a test-only, low-blast-radius diff; no production defect was exposed

## Coverage

Target: `scripts/langchain/followup_issue_generator.py`

- Before: 846 statements, 130 missed; 390 branches, 57 partial; **81.80%**
- After: 846 statements, 74 missed; 390 branches, 38 partial; **89.81%**
- Improvement: 75 statement/branch gaps covered, exceeding this round’s ~60-unit goal.

## Deliberate break/revert proof

Each new test was run against a targeted temporary regression and failed, then the exact production code was restored before the final green run:

- `test_extract_verification_data_preserves_supported_mixed_formats`: disabled `@` confidence parsing → failed.
- `test_json_and_markdown_helpers_preserve_machine_and_human_output`: forced `_extract_json()` to return `{}` → failed.
- `test_append_advisory_notes_only_adds_a_single_notes_section`: removed existing Notes guard → failed.
- `test_disposition_reports_absent_structured_provider_evidence`: replaced absent-evidence message → failed.
- `test_main_reads_file_inputs_and_writes_json_output`: bypassed codex-log file read → failed.
- `test_main_reads_verification_from_standard_input`: bypassed stdin read → failed.

## Validation

- `/opt/anaconda3/bin/python3 -m pytest tests/test_followup_issue_generator.py --cov=scripts.langchain.followup_issue_generator --cov-branch --cov-report=term-missing:skip-covered --no-cov-on-fail` — 160 passed; 89.81% target coverage.
- `/opt/anaconda3/bin/python3 -m ruff check tests/test_followup_issue_generator.py` — passed.
- `git diff --check` — passed.

Refs #3956

<!-- pr-preamble:start -->
<!-- meta:issue:3956 -->
> **Source:** Issue #3956

Closes #3956

<!-- pr-preamble:end -->

<!-- auto-status-summary:start -->
## Automated Status Summary
#### Scope
Workflows reads 81.75% blended line+branch in CI; reaching 90% needs about 4830 more covered statements+branches. Prioritize fleet's largest gap by far.

The target order below is the Orchestrator's own ranking (escaped defects, then churn, then uncovered mass -- unchanged). Only the bundling is new: earlier rounds spent a whole PR on files with a handful of uncovered statements, so one PR now covers the next ranked targets until it has covered about 60 units.

#### Tasks
- [x] Cover `scripts/langchain/followup_issue_generator.py` (225 uncovered statements+branches): write tests under `tests/` for its untested lines and branches.
- [x] For each new test, run the break-and-revert proof (break the code it covers, `pytest` fails; revert, `pytest` passes) and record both results in the PR body.
- [x] If a test exposes a real bug in a target above, fix it with the smallest diff and show `pytest tests/` green again.
- [x] Open ONE PR whose body states each target's coverage before and after (from `pytest --cov`) and has a closing line for THIS issue (`Closes #<this issue's number>`), so the round closes when the PR merges.

#### Acceptance criteria
- [x] `pytest` passes in CI with the new tests, and each new test fails when the code it covers is deliberately broken (the PR body shows the break-and-revert run).
- [x] The PR's Gate coverage shows the targets' uncovered statements+branches down by about 60 or more, or the PR body explains each target that could not be meaningfully covered.
- [x] Production code changes only where a test found a real bug, each one explained in the PR body.

- [x] Same contract as every round in this initiative:
1. [x] Pick the next target by the repo's own coverage-gap ranking (escaped-defect priority, then
   churn, then uncovered mass), not by file size.
2. [x] Every new test must FAIL when the code it covers is deliberately broken and PASS when
   reverted -- run that break-and-revert for real and report it, don't assert it.
3. [x] Real bugs found while writing tests get fixed with a minimal, targeted diff in the same PR,
   not worked around. Watch for the negative-cache pattern (cache.get(key) is None used as a 'not yet cached' check, which can't tell 'never queried' from 'queried and got nothing') -- it has recurred independently four separate times fleet-wide already.
4. [x] Low blast radius only -- test-only or tightly-scoped fixes, no refactors.
5. [x] One PR per logical chunk of work.

- [x] The goal is to improve the code, not a metric. If you measure this repo at or above 90% before
- [x] starting, say so in a comment on this issue and close it without opening a PR -- do not
- [x] manufacture a fix just because a round was requested.

<!-- auto-status-summary:end -->

## Registry routing replacement
Supersedes #3957 at unchanged implementation head `2b8bd54507eac399193eee67be690f2f0bb1817e`. The original coverage-autopilot agent completed with rc0 and released its claim before this routing repair. GitHub branch rename did not retarget the original PR, so this replacement uses the registry branch and concrete Codex routing. No implementation change or new issue is introduced.

### Remaining bounded review task
- [x] Address https://github.com/stranske/Workflows/pull/3957#discussion_r4298357592 in `tests/test_followup_issue_generator.py`: assert the captured `verification_data` contains the PASS verdict in the file-input CLI test; prove the assertion fails when that branch does not consume the verification file and restore the behavior. Do not mark this done based only on the old file/stdin test's unrelated assertions.

Actual current-head CI remains authoritative. Preserve the original coverage and break/revert receipts. This replacement carries no automatic review approval, resolved-thread claim or merge authorization. Closes #3956.

## Task reconciliation (2026-10-16)

Reviewed commits `2b8bd545` through `89751a76`: only `tests/test_followup_issue_generator.py` and evidence files changed. Issue #3956 explicitly selects this target using the Orchestrator ranking: 21 escaped-defect signals, churn 27, and 225 uncovered units. This verifies contract item 1 without selecting another target. No production changes or real bug fixes were needed (item 3); the diff remains test-only (item 4) within this existing PR (item 5). Item 2 is verified by the 29 actual RED/GREEN pairs recorded below, covering all 15 new test functions and every parameter case.

Latest committed coverage receipt: 178 passing target tests, **94.98%** blended target coverage (846 statements, 30 missing; 390 branches, 32 missing). The preceding iteration measured 92.64%, with 29 further units covered. Eight actual RED/GREEN pairs and exact mutations are recorded in `docs/evidence/issue-3956/followup-coverage-proof.json`; details in `followup-coverage-round.md`. These target figures do not establish repository-wide 90% coverage.


## Complete break/revert reconciliation

All 15 new test functions (25 parameterized test cases) have actual mutation/restore receipts, including the verification-file PASS assertion from review. Twenty-nine RED runs exited 1 with assertion failures; all 29 restored GREEN runs exited 0. Each selected test was run separately using `pytest <test-id> -m "not slow" -q`. Exact replacements, complete output, and source SHA256 are in `docs/evidence/issue-3956/followup-reconciliation-proof.json`.

| Test / case | RED | Restored GREEN |
| --- | --- | --- |
| `test_extract_verification_data_preserves_supported_mixed_formats` (test_extract_verification_data_preserves_supported_mixed_formats) | 1 failed | 1 passed |
| `test_json_and_markdown_helpers_preserve_machine_and_human_output` (test_json_and_markdown_helpers_preserve_machine_and_human_output) | 1 failed | 1 passed |
| `test_append_advisory_notes_only_adds_a_single_notes_section` (test_append_advisory_notes_only_adds_a_single_notes_section) | 1 failed | 1 passed |
| `test_disposition_reports_absent_structured_provider_evidence` (test_disposition_reports_absent_structured_provider_evidence) | 1 failed | 1 passed |
| `test_main_reads_file_inputs_and_writes_json_output` (cli-codex-file) | 1 failed | 1 passed |
| `test_main_reads_file_inputs_and_writes_json_output` (cli-verification-file-PASS) | 1 failed | 1 passed |
| `test_main_reads_verification_from_standard_input` (test_main_reads_verification_from_standard_input) | 1 failed | 1 passed |
| `test_generate_followup_without_available_clients_preserves_actionable_feedback` (test_generate_followup_without_available_clients_preserves_actionable_feedback) | 1 failed | 1 passed |
| `test_generate_followup_routes_available_clients_without_losing_model_identity[both]` (test_generate_followup_routes_available_clients_without_losing_model_identity[both]) | 1 failed | 1 passed |
| `test_generate_followup_routes_available_clients_without_losing_model_identity[reasoning]` (test_generate_followup_routes_available_clients_without_losing_model_identity[reasoning]) | 1 failed | 1 passed |
| `test_generate_followup_routes_available_clients_without_losing_model_identity[standard]` (test_generate_followup_routes_available_clients_without_losing_model_identity[standard]) | 1 failed | 1 passed |
| `test_followup_metadata_fallback_preserves_context_and_number_precedence[explicit-pr]` (test_followup_metadata_fallback_preserves_context_and_number_precedence[explicit-pr]) | 1 failed | 1 passed |
| `test_followup_metadata_fallback_preserves_context_and_number_precedence[explicit-issue]` (test_followup_metadata_fallback_preserves_context_and_number_precedence[explicit-issue]) | 1 failed | 1 passed |
| `test_followup_metadata_fallback_preserves_context_and_number_precedence[env-pr]` (test_followup_metadata_fallback_preserves_context_and_number_precedence[env-pr]) | 1 failed | 1 passed |
| `test_followup_metadata_fallback_preserves_context_and_number_precedence[env-issue]` (test_followup_metadata_fallback_preserves_context_and_number_precedence[env-issue]) | 1 failed | 1 passed |
| `test_followup_metadata_fallback_preserves_context_and_number_precedence[invalid-env]` (test_followup_metadata_fallback_preserves_context_and_number_precedence[invalid-env]) | 1 failed | 1 passed |
| `test_followup_metadata_fallback_preserves_context_and_number_precedence[missing-env]` (test_followup_metadata_fallback_preserves_context_and_number_precedence[missing-env]) | 1 failed | 1 passed |
| `test_invoke_without_langchain_uses_plain_prompts_and_preserves_output[configured]` (configured) | 1 failed | 1 passed |
| `test_invoke_without_langchain_uses_plain_prompts_and_preserves_output[fallback]` (fallback) | 1 failed | 1 passed |
| `test_invoke_without_langchain_reports_plain_prompt_failure_with_cause` (failure-cause) | 1 failed | 1 passed |
| `test_trace_failures_preserve_generated_text_and_log_the_cause[missing-module]` (missing-trace-module) | 1 failed | 1 passed |
| `test_trace_failures_preserve_generated_text_and_log_the_cause[extract-error]` (trace-error) | 1 failed | 1 passed |
| `test_llm_rounds_forward_evidence_and_assemble_issue_with_optional_traces[populated]` (issue-traces) | 1 failed | 1 passed |
| `test_llm_rounds_forward_evidence_and_assemble_issue_with_optional_traces[empty]` (empty-task-title) | 1 failed | 1 passed |
| `test_structured_followup_keeps_structural_findings_and_caps_non_actionable_history` (history-cap) | 1 failed | 1 passed |
| `test_main_bounds_concern_diagnostics_without_truncating_generated_tasks` (cli-concern-count-cap) | 1 failed | 1 passed |
| `test_main_bounds_concern_diagnostics_without_truncating_generated_tasks` (cli-concern-length-cap) | 1 failed | 1 passed |
| `test_main_bounds_concern_diagnostics_without_truncating_generated_tasks` (cli-all-concerns-reach-tasks) | 1 failed | 1 passed |
| `test_main_bounds_concern_diagnostics_without_truncating_generated_tasks` (cli-inline-original-criteria) | 1 failed | 1 passed |

Fresh matched coverage: **94.98% → 95.47%**, with missing statements **30 → 27** and missing branches **32 → 29** (6 additional covered units). Command: `pytest tests/test_followup_issue_generator.py --cov=scripts.langchain.followup_issue_generator --cov-report=term-missing -m "not slow" -q`; 179 passed. This is target coverage, not repository-wide coverage.

Related validation: `pytest tests/test_followup_issue_generator.py tests/test_verdict_policy.py tests/test_verdict_policy_integration.py tests/scripts/test_verifier_config.py -m "not slow" -q` — **239 passed**. Changed-file Black, Ruff, and `git diff --check` passed. No real production bug was exposed.

Run blockers: the mandatory repository-wide Black check failed with `PermissionError` at the multiprocessing forkserver socket; a single-worker retry timed out. `git add` failed creating `.git/index.lock` on the read-only filesystem, so this iteration is uncommitted. The PR-body update was rejected because the connector requires approval and this run has approval policy `never`; this file is a prepared replacement, not a claim that GitHub was updated. Read-only GitHub verification found PR #3960 open with `isDraft=false`. The full repository suite and hosted CI were not rerun locally.
