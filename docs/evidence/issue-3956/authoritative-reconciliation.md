# Authoritative coverage and mutation reconciliation — issue #3956

Checked 2026-11-03 (America/Chicago). This replaces the overlapping narratives in
`pr-body-reconciled.md`, `followup-review-correction.md`, and historical receipts.
Historical records remain intact; their coverage figures are superseded by the matched
**focused local** comparison below. Hosted Gate evidence is identified separately by
exact tested revision and artifact. A local run never establishes hosted Gate success.

## Exact revisions and scope

| Role | Revision |
| --- | --- |
| Baseline parent of #3960 | `94d9f952dad19f4f8048ae82bb8301bc6baf6ef5` |
| Merge #3960 | `314895ec5d0b1e102fc80aff8001eae2545ed7fa` |
| Original repair implementation | `7bcca99bc` | Inline guard restore and helper-only test removal |
| Measured repair source/tests (main incorporated) | `db91da15d7c44e34dca7d4f3d74e5cae62fff62c` | Final source for coverage, mutations, and Gate target |

Work merged from `closer/issue-3956` (PR #4401), `closer-r1/issue-3956` (coverage
JSON and retained-mutation reruns), and `closer-r3/issue-3956` (this head). Commits
`7bcca99bc` and `f77be1eee` are retained. Discarded: nothing from those branches
conflicted with the helper removal or defect fixes. No production fix from #3960 is
redone or reverted.

## One matched focused local comparison

Repository-selected runtime: `/opt/anaconda3/bin/python3` (Python 3.12.2),
pytest 9.1.1, coverage 7.16.2. All three snapshots use identical current
`pyproject.toml` settings (SHA256
`f793630708820650e709e2976674cfdd5fab636f974ec1bb9e54b5968026a402`),
with each revision's source, tests, and support modules. Command:

```sh
/opt/anaconda3/bin/python3 -m pytest tests/test_followup_issue_generator.py -q -o addopts= --cov=scripts.langchain.followup_issue_generator --cov-branch --cov-report=term-missing --cov-report=json
```

`coverage json` reads that run's data to obtain **missing branches**, rather than
substituting the terminal report's partial-branch count. Full output, source/test
hashes, missing lines/arcs, configuration revision and summaries are in
[local-coverage-comparison.json](local-coverage-comparison.json).

| Focused local snapshot | Passed | Statements | Missing statements | Branches | Missing branches | Missing statements + branches | Combined |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline `94d9f952` | 154 | 844 | 129 | 388 | 94 | 223 | 81.90% |
| Merge `314895ec` | 200 | 852 | 0 | 386 | 0 | 0 | 100.00% |
| Repair `db91da15d` | 199 | 851 | 0 | 386 | 1 | 1 | 99.92% |

The authoritative baseline → final reduction is **222 missing statement/branch
units (223 → 1)**. These are replacement snapshots; overlapping iterations are
never summed. The baseline terminal **BrPart=56** counts partially executed
branch sites, not the **94 missing arcs**. The old 129+56 calculation is superseded.
The merge also changed the source denominator; the repair removes one helper
statement and restores a defensive branch. A smaller denominator is not additional
test coverage.

This local comparison shares branch/exclusion configuration with Gate but is
**not** the hosted Gate execution: hosted Gate uses Python 3.14 coverage, marker
filtering `not quarantine and not slow`, and xdist on its full selected test scope.
The owner prohibited local full-suite/release/verify execution, so none was run.

### Defensive branch deliberately left uncovered

In `_guard_payloads`, falsy `label` skips source annotation (`124->126`). The payload
list uses fixed nonempty labels `verification_comment`, `original_issue`, and
`codex_log`. The branch is defensive; no current public input reaches it. The
repair restores the original inline logic and removes `_blocked_reason_with_source`
and only its helper-only empty-label test. The retained nonempty-label regression
proves observable blocked reasons contain their payload source. No frame mutation
or production extraction is used to force 100% coverage.

## Production defects retained from #3960

- **OSError:** `Path(value).is_file()` may raise (for example ENAMETOOLONG on long
  inline arguments), and `read_text()` may fail. `_read_existing_file` catches
  OSError; verification/original-issue arguments retain their literal text through
  `_load_text_arg`, while an unreadable optional Codex log becomes `None`. Both probe
  and read failures have retained tests and current-source mutation receipts.
- **Numbered checklist:** PR-meta refresh produced numbered unchecked items but the
  parse/merge regexes recognized only dash bullets. Checked state was lost on the
  next refresh. The source and consumer-template fixes and both numbered checklist
  regressions remain. Current repair changes no JS production or test bytes.

These were real production fixes, so historical “production unchanged” / “test-only”
claims describe earlier iterations only and do not describe #3960 as delivered.

## Ranking provenance

**Issue #3956 supplied the target ranking** (escaped-defect priority, then churn,
then uncovered mass). This repair follows that supplied target; it does not claim
an independently reproduced ranking or a new ranking run. No additional target is
introduced.

## Every retained added Python test and parameter case

Comparing the baseline test AST with repair leaves **35 added functions / 45
collected cases** after removing the helper-only test. The complete current-source
index is [retained-mutation-reconciliation.json](retained-mutation-reconciliation.json).
Each proof records the precise node ID (including parameter ID), mutation text,
mutant/restored source hashes, exact source revision/test hash, assertion failure
output, and restored passing output. All 50 mutation receipts were rerun on the
repair source; this includes source-invalidated CLI receipts that previously
mutated direct Path reads removed by the OSError fix. One mutation initially
selected the wrong Concerns parser and survived; its corrected replacement kills
the plain-label parser regression. Three re-raise mutations produced OSError
failures, so they were replaced with wrong-value mutations that produce actual
assertion failures. All four discarded attempts remain in the JSON and are not
counted among the 50 successful receipts.

1. `test_extract_verification_data_preserves_supported_mixed_formats`
2. `test_json_and_markdown_helpers_preserve_machine_and_human_output`
3. `test_append_advisory_notes_only_adds_a_single_notes_section`
4. `test_disposition_reports_absent_structured_provider_evidence`
5. `test_main_reads_file_inputs_and_writes_json_output`
6. `test_main_reads_verification_from_standard_input`
7. `test_main_bounds_concern_diagnostics_without_truncating_generated_tasks`
8. `test_generate_followup_without_available_clients_preserves_actionable_feedback`
9. `test_generate_followup_routes_available_clients_without_losing_model_identity` (parametrize)
10. `test_followup_metadata_fallback_preserves_context_and_number_precedence` (parametrize)
11. `test_invoke_without_langchain_uses_plain_prompts_and_preserves_output` (parametrize)
12. `test_invoke_without_langchain_reports_plain_prompt_failure_with_cause`
13. `test_trace_failures_preserve_generated_text_and_log_the_cause` (parametrize)
14. `test_llm_rounds_forward_evidence_and_assemble_issue_with_optional_traces` (parametrize)
15. `test_structured_followup_keeps_structural_findings_and_caps_non_actionable_history`
16. `test_confidence_helpers_preserve_empty_integer_and_percent_provider_edges`
17. `test_advisory_unfalsifiable_and_spurious_concern_filters`
18. `test_missing_concerns_note_triggers_for_empty_body_and_blank_verdicts`
19. `test_strip_checkbox_preserves_non_list_text`
20. `test_budget_followup_tasks_stops_when_next_task_would_exceed`
21. `test_truncate_task_to_budget_returns_task_when_already_within_budget`
22. `test_code_change_decision_skips_split_and_advisory_only_concerns`
23. `test_build_why_section_resolves_verdict_when_omitted`
24. `test_invoke_llm_records_langsmith_trace_url`
25. `test_get_followup_client_falls_back_when_reasoning_model_unavailable`
26. `test_main_guard_blocked_writes_markdown_output_file`
27. `test_concern_label_and_insights_skip_short_and_spurious_fragments`
28. `test_parse_checklist_skips_direct_checkbox_placeholders_and_non_list_lines`
29. `test_select_followup_acceptance_criteria_keeps_all_when_feedback_mentions_sync`
30. `test_select_followup_acceptance_criteria_falls_back_when_mixed_filter_empties`
31. `test_module_main_entrypoint_invokes_main`
32. `test_guard_payloads_annotates_reason_with_nonempty_label`
33. `test_read_existing_file_returns_none_when_is_file_raises_oserror`
34. `test_read_existing_file_returns_none_when_read_text_raises_oserror`
35. `test_main_oserror_fallbacks_keep_literal_args_and_drop_codex_log`


### Historical receipt index (preserved, superseded by the current-source reruns)

| Retained function range above | Actual historical receipt | Notes |
| --- | --- | --- |
| 1–15 | `followup-reconciliation-proof.json` | 29 mutations, 15 functions; provider `[both, reasoning, standard]`, metadata `[explicit-pr, explicit-issue, env-pr, env-issue, invalid-env, missing-env]`, invocation `[configured, fallback]`, trace `[missing-module, extract-error]`, LLM `[populated, empty]` cases explicitly indexed |
| 16–26 | `followup-edge-coverage-proof.json` → `results` | 11 functions, actual assertion failures and restored passes |
| 27–29 | `followup-contract-edge-proof.json` → `proofs` | 3 functions; historical exit-only claims replaced by captured current assertion failures |
| 30–31 | `followup-remaining-branches-proof.json` → `proofs` | 2 functions; current assertion output now retained |
| 32 | `followup-guard-nonempty-label-repair-proof.json` | Inline guard replacement proof; rerun again in current index |
| 33–35 | `followup-oserror-fallback-proof.json` → `proofs` | Probe/read/literal fallback tests; all current assertion outputs now retained |

The prior assertion that `followup-reconciliation-proof.json` covers items 1–31
was false. It covers only 1–15. The prior blanket claim that all recorded source
paths remained valid was also false for direct CLI Path reads; the current reruns
mutate `_load_text_arg` / `_read_existing_file` callers instead.

The two retained added JS tests and their separate mutations are indexed in
[numbered-checklist-repair-proof.json](numbered-checklist-repair-proof.json):
`parseCheckboxStates captures numbered checklist completions` and
`mergeCheckboxStates restores numbered contract checklist items across refresh`.
Each independently fails with an assertion when its regex loses numbered support,
then passes after restoration. Historical `numbered-checklist-state-proof.json`
remains the earlier receipt; its coverage/completion narrative is superseded here.

### Superseded claims and records

- `followup-blocked-reason-helper-proof.json`: helper removed; proof no longer applies.
- `followup-empty-label-proof.json`: caller-frame empty-label test abandoned.
- `followup-coverage-proof.json`, `followup-reconciliation-proof.json`,
  `followup-edge-coverage-proof.json`, `followup-contract-edge-proof.json`,
  `followup-remaining-branches-proof.json`, `followup-oserror-fallback-proof.json`,
  `numbered-checklist-state-proof.json`, `followup-coverage-round.md`,
  `followup-review-correction.md`, and `pr-body-reconciled.md`: retained historical
  snapshots, not final coverage or completion evidence; current receipts above
  replace their mutation reconciliation claims.
- Merge-era 100% figures used the helper-only test and do not describe repair.
- Historical closing statements do not establish issue completion. This repair
  uses **Refs #3956**; the issue remains subject to the closer's acceptance.

## Local verification output (measured repair revision above)

```text
........................................................................ [ 36%]
........................................................................ [ 72%]
.......................................................                  [100%]
================================ tests coverage ================================
_______________ coverage: platform darwin, python 3.12.2-final-0 _______________

Name                                            Stmts   Miss Branch BrPart   Cover   Missing
--------------------------------------------------------------------------------------------
scripts/langchain/followup_issue_generator.py     851      0    386      1  99.92%   124->126
--------------------------------------------------------------------------------------------
TOTAL                                             851      0    386      1  99.92%
199 passed in 1.84s
```

```sh
node --test .github/scripts/__tests__/agents-pr-meta-update-body.test.js
```

```text
✔ closing-keyword and branch sources retain closing intent across two body syncs (2.522ms)
ℹ tests 170
ℹ suites 0
ℹ pass 170
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 3212.901417
```

## Hosted verification

Earlier repair head `f77be1eee61239aa264c166aed84db8fae8708f3` has
[successful Gate run 41567623097](https://github.com/stranske/Workflows/actions/runs/41567623097)
and [Selftest CI run 41567622897](https://github.com/stranske/Workflows/actions/runs/41567622897).
Those runs tested that head only.

Downloaded and inspected [Gate Python 3.14 coverage artifact 13200231583](https://github.com/stranske/Workflows/actions/runs/41567623097/artifacts/13200231583)
for `f77be1eee`: 851 statements, 0 missing statements, 386 branches, **1 missing
branch**, 99.92%. ZIP SHA256:
`540949b4d94392b5d2daafc794f9acc6c1011155ac0cc24bf8f1bb6d635f4136`.
Summary in [hosted-coverage-receipt.json](hosted-coverage-receipt.json).

**Branch tip `closer-r3/issue-3956`** adds only evidence docs atop `db91da15d`; hosted
Gate/selftest for the exact pushed head are recorded in PR #4401 (supersedes the
`f77be1eee` run for merge approval once green).
