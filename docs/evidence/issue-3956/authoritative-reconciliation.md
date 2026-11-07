# Authoritative coverage and mutation reconciliation — issue #3956

## Current delivery readback (2026-11-07 UTC)

Before changing source or tests in this round, attempted:

```sh
gh pr view 4401 --repo stranske/Workflows --json state,headRefOid,mergeStateStatus,reviewDecision,statusCheckRollup
```

The command exited 1: `error connecting to api.github.com`. Connected GitHub
read-only tools supplied the fallback inspection of PR metadata, all submitted
reviews, inline review threads, changed files, and commit-associated workflow runs.
PR #4401 remains OPEN, `isDraft=false`, at
`9eaf43313c0e57ef964e4171f645985dca5742b8`; `merged=false`, `merged_at=null`.
REST `mergeable=true` does not establish GraphQL `mergeStateStatus`, review
approval, or permission to merge. The REST `merge_commit_sha` field on this open
PR is a test merge, not a delivered main revision.

The actual identified review blocker is active unresolved thread
`PRRT_kwDOQprj9M6zZ4AB` (comment 4462444583): the revision table declares two
columns but supplies three cells, hiding repair/source notes. Two other unresolved
threads are outdated (`PRRT_kwDOQprj9M6y9cVz`, `PRRT_kwDOQprj9M6y9cWG`), about
local/hosted labeling and receipt mapping. All three submitted reviews are
COMMENTED; none establishes an approval or a changes-requested decision.
Commit-associated Gate run `41752024615` and Selftest CI run `41752024817` report
success. That discovery returns only the first page of pull-request runs and is
not a complete expected/required-check receipt. Final delivery remains pending
review settlement, complete exact-head gate verification, merge and main readback.

Main was also read through the connected GitHub file API: lines 100–145 of
`scripts/langchain/followup_issue_generator.py` still define and call
`_blocked_reason_with_source` (blob `c3a19cbf41a476954b8afcde6d214b3cf8c82a00`).
That branch-relative read establishes the missing behavior at readback time;
it does not pin an immutable main commit. Final main acceptance is unsatisfied.

Repeated readback before the numbered-checklist test changes in this round:
the requested CLI read again exited 1 connecting to `api.github.com`. Connected
GitHub metadata still reports #4401 OPEN, ready for review, at the same full head
above, with no merge date. All three reviews remain COMMENTED; the same one
non-outdated unresolved table thread and two outdated threads remain. PR #3960's
complete changed-filename list independently confirms all three Node paths named
below. The injected task list's checked merge task conflicts with this readback
and must not be treated as completed delivery.

The repeated main read is now pinned: resolving `main` returned
`d2106cc83e060d0063f63dd08ea94bbaa4104fbf`. Reading the generator at that exact
commit returned blob `c3a19cbf41a476954b8afcde6d214b3cf8c82a00`; lines 105–115
still define the helper and line 138 calls it. This immutable main read confirms
that the inline-guard repair has not been delivered at the inspected revision.

The following historical measurements were checked 2026-11-03 (America/Chicago).
This record replaces the overlapping narratives in
`pr-body-reconciled.md`, `followup-review-correction.md`, and historical receipts.
Historical records remain intact; their coverage figures are superseded by the matched
**focused local** comparison below. Hosted Gate evidence is identified separately by
exact tested revision and artifact. A local run never establishes hosted Gate success.

## Exact revisions and scope

| Role | Revision | Notes |
| --- | --- | --- |
| Baseline parent of #3960 | `94d9f952dad19f4f8048ae82bb8301bc6baf6ef5` | Original baseline |
| Merge #3960 | `314895ec5d0b1e102fc80aff8001eae2545ed7fa` | Original delivery |
| Original repair implementation | `7bcca99bc` | Inline guard restore and helper-only test removal |
| Measured repair source/tests | `db91da15d7c44e34dca7d4f3d74e5cae62fff62c` | Main was incorporated into the repair branch; this is not delivery to main |
| Prior local source snapshot | `a9fb48a0c90308a13c8f09ac01ac57d9dc309a45` | Same generator and target-test hashes as measured repair; the prior round added the auditor separately |
| Numbered-checklist validation base | `a5145aafbe1cf8bc6fc69bf6961eaf18a91b69d4` | Production bytes unchanged; new Node tests identified by the supplemental receipt's test hash |

Historical repair work was integrated from `closer/issue-3956` (PR #4401),
`closer-r1/issue-3956` (coverage JSON and retained-mutation reruns), and
`closer-r3/issue-3956`. This describes branch integration, not a merged PR. Commits
`7bcca99bc` and `f77be1eee` are retained. Discarded: nothing from those branches
conflicted with the helper removal or defect fixes. No production fix from #3960 is
redone or reverted.

**Historical PR #4401 inspection:** The earlier CLEAN/no-blocker statement is
superseded by the current readback above. Checked PR-body boxes are claims, not
evidence of merge or acceptance. The measured repair revision below identifies
source bytes; it does not establish delivery to main.

## One matched focused local comparison

Historical local runtime: `/opt/anaconda3/bin/python3` (Python 3.12.2),
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

The matched local baseline → repair reduction is **222 missing statement/branch
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
  regressions remain. PR #4401 changes no JS production or test bytes; the later
  local validation below adds two tests for the existing whitespace boundary.
  PR #3960's file list locates the implementation at
  `.github/scripts/agents_pr_meta_update_body.js`, its identical consumer copy at
  `templates/consumer-repo/.github/scripts/agents_pr_meta_update_body.js`, and tests
  at `.github/scripts/__tests__/agents-pr-meta-update-body.test.js`.
  **Existing whitespace difference:** `parseCheckboxStates` accepts arbitrary
  whitespace after a bullet through `(?:[-*+]|\d+[.)])\s+\[(x| )\]`.
  `mergeCheckboxStates` uses `([-*+]|\d+[.)]) \[( )\]`, with exactly one literal
  space between the bullet and checkbox. Both recognize numbered bullets; their
  whitespace contracts still differ. This round records that difference and
  preserves both regexes without expanding scope into a whitespace repair.

These were real production fixes, so historical “production unchanged” / “test-only”
claims describe earlier iterations only and do not describe #3960 as delivered.

## Ranking provenance

**Issue #3956 supplied the target ranking** (escaped-defect priority, then churn,
then uncovered mass). This repair follows that supplied target; it does not claim
an independently reproduced ranking or a new ranking run. No additional target is
introduced.

**Owner-visible limitation:** The canonical ranking inputs and original ranking
execution are unrecoverable from these receipts. Historical numbers (21 escaped
defect signals, churn 27, 225 uncovered units) are supplied claims, not independently
verified ranking results. `followup-coverage-round.md` explicitly records the
missing canonical ranking and rejects issue-3743 proxy artifacts as substitutes.
The contradictory checked ranking boxes in `pr-body-reconciled.md` and historical
JSON contracts are superseded: independent ranking verification remains incomplete.

## Coverage values and contradictory completion claims

| Value | Historical attribution | Supported interpretation |
| --- | --- | --- |
| 81.80% | `pr-body-reconciled.md`, early local baseline: 846 statements, 390 branches | Historical local claim; exact tested revision, JSON missing arcs, and hosted run/artifact binding are unsupported. It is not the matched 81.90% baseline. |
| 89.81% | Same document, early local 160-test snapshot, 74 missing statements and 38 partial branch sites | Historical local claim with a command; exact source revision and hosted binding unsupported. |
| 99.11% | `followup-edge-coverage-proof.json` and the before-value in `followup-contract-edge-proof.json` | Intermediate local claim tied to source hash `251c5642…`, with 846 statements and 390 branches in the adjacent narrative; no exact tested commit or hosted artifact supports this percentage. |
| 100% | Matched merge snapshot `314895ec…` in `local-coverage-comparison.json`: 852 statements, 386 branches, zero misses | Supported focused-local merge measurement, including the helper-only test; historical empty-label/helper/OSError receipts also claim 100% at different denominators. None establishes the repaired main state. |
| 99.92% | Matched repair `db91da15…`, historical hosted `f77be1ee…`, and this round's focused-local rerun | Separately identified local/hosted measurements; repaired source retains one missing defensive arc. |

The old **75-unit** claim subtracts `(130 + 57) - (74 + 38)`, mixing missing
statements with partial branch sites. It cannot prove approximately 60 missing
statement/branch destinations were removed. The comparable JSON local snapshots
measure **(129 + 94) - (0 + 1) = 222** missing statement/branch-destination units.
No comparable hosted baseline artifact is present in the inspected evidence, so
the hosted approximately-60-unit criterion remains **incomplete**. Local 222 is
explicitly separate and cannot fill that gap.

Checked CI, coverage, ranking, exhaustion and completion boxes in
`pr-body-reconciled.md`, historical proof contracts and PR #4401's body are
superseded where they claim more than the evidence above. The earlier
`followup-coverage-round.md` is an intermediate 170→178-test, 29-unit local round
(92.64%→94.98%), not the final delivery. Its test-only statement describes that
iteration. `followup-review-correction.md` describes an abandoned frame-based test
and later helper extraction; this repair removes the helper again. The OSError
fallback and numbered-checklist changes are production fixes. Original historical
receipts, including unsupported claims, remain intact for traceability.

The follow-up inspection read `followup-coverage-round.md` in full, the OSError,
empty-label, helper, nonempty-label, contract-edge, remaining-branch and numbered
state proofs, and the coverage/ranking/contract fields of the larger historical
proofs. Their mutation bodies remain subject to the bounded retained audit above;
this inspection does not upgrade historical exit-only claims into assertion proof.
Specific conflicting claims are superseded as follows:

| Historical receipt | Conflicting claim | Authoritative disposition |
| --- | --- | --- |
| `followup-coverage-round.md` and `followup-coverage-proof.json` | Test-only 170→178-test round, 92.64%→94.98%, 29 units | Describes an earlier local iteration, not the final #3960 diff or hosted coverage. The round explicitly reports canonical ranking unavailable. |
| `followup-oserror-fallback-proof.json` | `3_no_production_bug_found=true`, ranking verified, no remaining work, 100% | The OSError fallback is a real production fix. Its own classification note rejects test-only scope. Ranking numbers are supplied claims; exit-only/re-raise proofs do not establish relevant assertion failures and are superseded by current-source wrong-value receipts. |
| `followup-contract-edge-proof.json`, `followup-remaining-branches-proof.json` and `followup-reconciliation-proof.json` | Ranked/test-only completion and intermediate coverage | Historical local stages at different source/test snapshots. The matched comparison and retained current-source audit govern; independent ranking remains unrecoverable. |
| `followup-empty-label-proof.json`, `followup-blocked-reason-helper-proof.json` and `numbered-checklist-state-proof.json` | Empty-label/helper-assisted 100%, target exhausted, checked ranking contract | Abandoned frame-based test and removed helper-only test cannot establish repaired coverage. Numbered-checklist behavior is retained; its generator coverage/exhaustion narrative is historical. |

No historical receipt is edited by this reconciliation. Recovering the canonical
ranking inputs and execution remains an owner-visible limitation, not a completed
ranking check.

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

### Bounded audit and unabridged replacements (2026-11-07)

The retained index was inspected in bounded groups (indices 0–4, 5–9, 10–16,
17–24, 25–34, 35–42, 43–49); the four discarded attempts and both Node receipts
were inspected separately. Mutation replacements, parameter-specific failing
assertions and restored summaries were read without accepting tool-output
truncation as inspection. The new read-only auditor also reconstructs every
mutant SHA256, checks restored source/test hashes, compares independently
collected cases against the baseline AST, and verifies assertion-failing RED
and single-case GREEN output. It never executes commands from receipt data.

The first audit exited 1: historical indices **2** (duplicate Notes section) and
**24** (five-item history cap) have pytest `Full output truncated` diagnostics.
Their original records remain unchanged. Both mutations were rerun independently
with `-vv --tb=long -m 'not slow'` in isolated temporary packages using the same
source/test bytes, original support modules, and the current Python 3.14.10.
Each failed with the relevant assertion (exit 1), then passed after exact source
restoration (exit 0). Full output, commands, revision, and binding to the original
receipt digest are in
[retained-mutation-unabridged-reruns.json](retained-mutation-unabridged-reruns.json).
The restored production file in the checkout was never mutated.

[retained-mutation-audit.json](retained-mutation-audit.json) enumerates every
Python parameter case and both Node cases, each replacement, assertion, restored
GREEN summary and historical receipt index. With the bound replacements the
audit exits 0: **35 added functions, 45 cases, 50 Python receipts, 2 Node receipts,
zero unmapped cases or invalid mutation hashes**. This verifies the inspected
repair source; it does not establish final main delivery.

Reproduction (from the repository root):

```sh
git show 94d9f952dad19f4f8048ae82bb8301bc6baf6ef5:tests/test_followup_issue_generator.py > /tmp/issue-3956-baseline-tests.py
python -m pytest -p no:langsmith_plugin tests/test_followup_issue_generator.py --collect-only -q -m 'not slow' > /tmp/issue-3956-collected-tests.txt
python scripts/audit_followup_mutations.py --baseline-tests /tmp/issue-3956-baseline-tests.py --collected-tests /tmp/issue-3956-collected-tests.txt
```

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

The historical receipt records download and inspection of
[Gate Python 3.14 coverage artifact 13200231583](https://github.com/stranske/Workflows/actions/runs/41567623097/artifacts/13200231583)
for `f77be1eee`: 851 statements, 0 missing statements, 386 branches, **1 missing
branch**, 99.92%. ZIP SHA256:
`540949b4d94392b5d2daafc794f9acc6c1011155ac0cc24bf8f1bb6d635f4136`.
Summary in [hosted-coverage-receipt.json](hosted-coverage-receipt.json).

The current publication head is `closer/issue-3956` at `9eaf43313…`, not the
historical `closer-r3/issue-3956` branch. Fresh hosted job-log inspection is recorded
separately in [hosted-gate-readback.json](hosted-gate-readback.json):

| Tested revision | Gate run | Python 3.14 job | Coverage artifact | Hosted pytest result |
| --- | --- | --- | --- | --- |
| `f77be1eee61239aa264c166aed84db8fae8708f3` | `41567623097` | `125693048153` | `13200231583` | 50,308 passed, 27 skipped, 3 xfailed |
| `9eaf43313c0e57ef964e4171f645985dca5742b8` | `41752024615` | `126320180581` | `13287665592` | 50,354 passed, 27 skipped, 3 xfailed |

Both logs show 851 statements, zero missing statements, 386 branches, one partial
branch site, `124->126`, and 99.92% for the generator. Runtime is Python 3.14.9;
coverage versions differ (7.17.0 versus 7.17.1). Artifact metadata binds the second
archive to `9eaf43313…`, digest
`b63903e319393d955daf6a879fc9a1ffe7fa5d088672c97ab253be5f6c2ae06a`.
The ZIP bytes were not inspected in this round; the new exact-head measurement
is supported by its hosted job log. The older JSON receipt remains distinct.

The logged command builder invokes `pytest -p ci_test_growth "${args[@]}"`.
Its reconstructed argument vector, using the logged marker/worker environment,
is below (the repeated xdist flags reflect the actual builder; the final ones win):

```sh
pytest -p ci_test_growth -m 'not quarantine and not slow' --junitxml=pytest-junit.xml --cov --cov-config=pyproject.toml --cov-report=xml:coverage.xml --cov-report=term-missing --cov-report=json:coverage.json -n auto --dist load -n 4 --dist=loadgroup
```

These hosted results concern repair snapshots only. No comparable original
hosted baseline has been recovered, and no main delivery is inferred from them.

## Prior local validation and remaining delivery work

This subsection preserves the prior agent round's results and commit blockers.
Automation subsequently recorded that work in `a5145aaf…`; the later numbered
checklist round and its independent commit attempt are recorded below.

Checkout source revision: `a9fb48a0c90308a13c8f09ac01ac57d9dc309a45`.
The generator and original target test file remain byte-for-byte unchanged in
this round. `git diff 314895ec… HEAD -- scripts/langchain/followup_issue_generator.py
tests/test_followup_issue_generator.py` confirms the existing repair only restores
inline annotation and removes the one helper-only test. The numbered-checklist
implementation and consumer copy compare identical.

The current selected interpreter is
`/opt/hostedtoolcache/Python/3.14.10/x64/bin/python` (Python 3.14.10), matching the
primary 3.14 runtime in `.github/workflows/ci-python-versions.env`.
The required target pytest invocation with `-m 'not slow'` initially exited 3
during optional LangSmith plugin startup: its use of deprecated
`asyncio.iscoroutinefunction` conflicts with the repository's warning-as-error
configuration. The isolated retry excludes that plugin; no test or assertion is
disabled. The original invocation is not represented as successful.

```sh
python -m pytest -p no:langsmith_plugin tests/test_followup_issue_generator.py -q -m 'not slow'
# 199 passed; exit 0
python -m pytest -p no:langsmith_plugin tests/test_followup_issue_generator.py -q -m 'not slow' --cov=scripts.langchain.followup_issue_generator --cov-report=term-missing --cov-report=json:/tmp/issue-3956-current-coverage.json
# 199 passed; 851 statements, 0 missing; 386 branches, 1 partial; 99.92%; 124->126
python -m pytest -p no:langsmith_plugin tests/test_followup_issue_generator.py tests/scripts/test_audit_followup_mutations.py -q -m 'not slow'
# 222 passed (199 generator + 23 auditor regression cases); exit 0
node --test .github/scripts/__tests__/agents-pr-meta-update-body.test.js
# exit 0; process-isolated reporter aggregates the file as one passing unit
node --test --test-isolation=none .github/scripts/__tests__/agents-pr-meta-update-body.test.js
# 170 individual tests passed, 0 failed, 0 skipped; exit 0
ruff check scripts/audit_followup_mutations.py tests/scripts/test_audit_followup_mutations.py
# All checks passed
black --line-length 100 scripts/audit_followup_mutations.py
black --line-length 100 tests/scripts/test_audit_followup_mutations.py
# Both formatted successfully using single-file invocations
git diff --check
# exit 0
```

The required repository-wide command
`black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .`
fails with a sandbox `PermissionError` binding the multiprocessing forkserver
socket. `BLACK_NUM_WORKERS=1` retries were stopped at 45 and 90 seconds (exit 124);
the latter reported 889 files unchanged but was aborted, so it is not a passing
repository-wide result. The formatting gate therefore prohibits a commit.
Staging the five original changed/new files also failed creating
`.git/index.lock`: **read-only file system**. All changes remain local and
uncommitted; no push, PR mutation, sync dispatch or merge was performed.

Current task accounting (local evidence only):

- [x] Inspect #4401 head, reviews and threads before source edits; record the actual blocker, with the `gh` transport failure disclosed.
- [x] Verify the existing inline-guard repair removes only the helper-only test and retains the OSError fix/tests.
- [x] Locate the Node files through #3960's file list and preserve their numbered-checklist behavior and existing whitespace difference.
- [x] Audit all retained mutation cases, replace the two truncated receipts with bound full-output reruns, and verify restored GREEN against the identified repair source.
- [x] Reconcile original delivery, repair, hosted snapshots, coverage units and unsupported baseline claims.
- [x] Supersede conflicting historical completion/test-only claims and expose unrecoverable ranking provenance.
- [x] Run targeted Python and Node validation and record the interpreter, command variants, revisions and results; the unmodified Python command's plugin-startup failure remains disclosed above.
- [ ] Complete existing #4401 review settlement, exact-head gate verification, merge and immutable main readback. The CLI final readback also failed to connect; connected metadata still reports OPEN, `isDraft=false`, unchanged head and `merged_at=null`.

Acceptance remains incomplete: main still has the helper; #4401 is open with an
active unresolved thread; the comparable hosted reduction is unproved; canonical
ranking provenance is unrecoverable; and the unmodified Python invocation has an
environment startup failure. The local table correction does not resolve the
thread on the remote repair PR until it is delivered and reviewed there.

## Numbered-checklist validation round (2026-11-07 UTC)

- [x] Inspect the PR #3960 Node file list, source, consumer copy and tests;
  preserve numbered handling and document the existing whitespace difference.
- [x] Inspect the historical round/OSError/remaining proof claims and supersede
  conflicting completion, test-only and ranking claims as recorded above.
- [ ] Deliver the repair through #4401's review, checks, merge and main readback.

The only source-code change in this round is two added Node tests in
`.github/scripts/__tests__/agents-pr-meta-update-body.test.js`:

1. `numbered checklist parsing accepts tabs and multiple spaces in source and template`
2. `numbered checklist merging retains its single-space boundary in source and template`

Both exercise the source and consumer exports, `1.` and multi-digit `12)` bullets,
one space, two spaces and a tab, indentation, unchecked items and fenced examples.
The merge test also checks already-completed items and repeated-refresh stability.
It uses an independently constructed state map so a parser failure cannot conceal
a merge regression. The existing two numbered tests remain unchanged. Generator
source/tests, both production Node copies, templates and the sync manifest have
no diff; no consumer payload changed.

[numbered-checklist-whitespace-proof.json](numbered-checklist-whitespace-proof.json)
maps both new tests to **8 assertion-failing RED / restored GREEN receipts**.
Production source is pinned to `a5145aafbe1cf8bc6fc69bf6961eaf18a91b69d4`,
SHA256 `3a549a854dbd2ee280c1a9d037d05e09b67e3dc35ed8571837468f442a57a15f`
for each copy. The new local test overlay is bound by its SHA256
`3283b5b921327890064b5aebe82c214427dc49d0bdf200712251b4d0a0819eab`.
Each selected test was run independently against a temporary module mutation,
then the exact restored bytes, with Node v24.22.2. Checkout production was never
mutated. Complete outputs were inspected in bounded pairs 0–1, 2–3, 4–5 and 6–7.

| Receipt indices (source / template) | Test | Mutation and observed assertion |
| --- | --- | --- |
| 0 / 4 | Parsing | Replace arbitrary bullet whitespace with one space; the two-space checked item disappears from the expected state map. |
| 1 / 5 | Merging | Widen the literal bullet space to arbitrary whitespace; a two-space item changes instead of remaining byte-identical. |
| 2 / 6 | Parsing | Drop right-parenthesis bullets; `12)` disappears from the expected state map. |
| 3 / 7 | Merging | Drop right-parenthesis bullets; `12)` stays unchecked instead of restoring completion. |

All eight RED runs exit 1 with `AssertionError [ERR_ASSERTION]`; all restored
GREEN runs exit 0 with one pass and zero failures. The original retained audit
continues to cover the original two Node cases; this supplement covers the two
new cases separately without rewriting historical evidence.

Validation against the identified base plus the hash-bound Node test overlay:

```sh
node --test .github/scripts/__tests__/agents-pr-meta-update-body.test.js
# exit 0; default process-isolated reporter aggregates one passing file
node --test --test-isolation=none .github/scripts/__tests__/agents-pr-meta-update-body.test.js
# exit 0; 172 passed, 0 failed, 0 skipped
python -m pytest tests/test_followup_issue_generator.py -q -m 'not slow'
# exit 3 during optional LangSmith plugin startup; no successful test run claimed
python -m pytest -p no:langsmith_plugin tests/test_followup_issue_generator.py -q -m 'not slow' --cov=scripts.langchain.followup_issue_generator --cov-report=term-missing --cov-report=json:/tmp/issue-3956-round-coverage.json
# exit 0; 199 passed; generator Cover 99.92%, 851 statements, 0 missing,
# 386 branches, 1 missing arc (124->126); selected Python 3.14.10
python scripts/audit_followup_mutations.py --baseline-tests /tmp/issue-3956-round-baseline-tests.py --collected-tests /tmp/issue-3956-round-collected-tests.txt
# exit 0; 35 added Python functions / 45 cases, 50 Python and 2 original Node
# receipts; complete=true, no problems. Inputs prepared as in reproduction above.
git diff --check
# exit 0
```

The original Python command's plugin startup failure remains an acceptance gap;
the isolated passing run and focused local coverage do not replace it or hosted
evidence. No Python files changed, so this round does not introduce a Python
formatting gate. Staging only the Node test, this reconciliation and its new
receipt failed creating `.git/index.lock` (**read-only file system**, exit 128).
This round's changes remain uncommitted; no push or remote PR change occurred.
#4401 remains open, ready for review at the readback head. Main still contains
the helper at the pinned commit, the hosted comparable reduction is unproved and
ranking provenance is unrecoverable. No delivery or overall acceptance checkbox
is completed by these local results.

## Task-status reconciliation before further tests (2026-11-07 UTC)

Reviewed commits `a9fb48a0`, `a5145aaf` and `3ab79ec1`. The last two commits
record the previously uncommitted audit and numbered-checklist work. The first
unchecked Node inspection task and the historical-proof inspection task are
already implemented and documented above; a fresh Node run at `3ab79ec1` passed
all 172 cases. Re-read the historical round and OSError receipt in full and the
remaining proof coverage/ranking/contract fields separately. Their contradictory
completion and test-only claims remain superseded, and ranking provenance remains
unrecoverable.

Before further code edits, the requested `gh pr view 4401` inspection again
exited 1 connecting to `api.github.com`. Connected metadata reports #4401 OPEN,
`draft=false`, unchanged head `9eaf43313c0e57ef964e4171f645985dca5742b8`,
`merged=false`, and `merged_at=null`. All three submitted reviews are COMMENTED.
Thread `PRRT_kwDOQprj9M6zZ4AB` remains unresolved and non-outdated; the other two
unresolved threads remain outdated. The checked merge task is therefore false.
No gate bypass or merge was attempted.

Attempted to update #4518's body to check the two verified inspection tasks and
uncheck the undelivered #4401 merge task. The connected GitHub update was denied:
`MCP tool call requires approval, but approval policy is never`. The remote body
was not changed. This is a local reconciliation, not a successful remote update.
The next local test will exercise numbered state through `buildStatusBlock`,
which composes normalization, parsing and merging during a real summary refresh.

### Summary-refresh test and verification

Added `buildStatusBlock preserves numbered completion through normalization and
repeated refresh` to the identified Node test file. It independently checks both
production exports through two summary rebuilds: numbered task and acceptance
completion survives tabs/multiple spaces and renumbering; pending items stay
unchecked despite checked examples in fenced code or outside the managed block.
The source and consumer regexes remain unchanged, including their different
whitespace contracts. No consumer payload, Python file or protected file changed.

[numbered-checklist-summary-proof.json](numbered-checklist-summary-proof.json)
binds this additional Node case to base `3ab79ec1275d150bd32a2a414cd99d9a28981ce0`
and test-overlay SHA256
`05e6d51fef76575be14a373c34decc374455959e7d5d7e94b201165cf65e8bfb`.
Both production copies retain SHA256
`3a549a854dbd2ee280c1a9d037d05e09b67e3dc35ed8571837468f442a57a15f`.
Receipts 0–1 mutate source parsing/merging; 2–3 independently mutate the template.
Each removes numbered support, fails the named test with the corresponding
source/template completion assertion (exit 1), then passes after exact byte
restoration (exit 0, one pass, zero failures). Read all four full outputs in
bounded pairs 0–1 and 2–3. Production mutations used disposable copies only.
These supplement the original retained mapping and whitespace receipts without
claiming any new main delivery.

One discarded exploratory mutation bypassed `ensureChecklist` for tasks and
survived: `coalesceWrappedChecklist` already normalizes the bullet whitespace.
The receipt records that survival separately; it is not counted as RED evidence.
The initial Node mutation driver could not spawn a child (`EPERM`); the Python
driver completed all four independent mutation/restore runs.

Validation on the named base plus the Node test overlay, using Node v24.22.2 and
`/opt/hostedtoolcache/Python/3.14.10/x64/bin/python`:

```sh
node --test .github/scripts/__tests__/agents-pr-meta-update-body.test.js
# exit 0; default reporter aggregates one passing file
node --test --test-isolation=none .github/scripts/__tests__/agents-pr-meta-update-body.test.js
# exit 0; 173 passed, 0 failed, 0 skipped
python -m pytest tests/test_followup_issue_generator.py -q -m 'not slow'
# exit 3; optional LangSmith plugin's deprecated asyncio.iscoroutinefunction
# fails during startup under warning-as-error settings
python -m pytest -p no:langsmith_plugin tests/test_followup_issue_generator.py -q -m 'not slow' --cov=scripts.langchain.followup_issue_generator --cov-report=term-missing --cov-report=json:/tmp/issue-3956-summary-coverage.json
# exit 0; 199 passed; generator Cover 99.92%, 851 statements, 0 missing,
# 386 branches, 1 missing arc (124->126)
git diff --check
# exit 0
```

Fresh immutable main read at `d2106cc83e060d0063f63dd08ea94bbaa4104fbf`
still shows `_blocked_reason_with_source` defined/called in generator blob
`c3a19cbf41a476954b8afcde6d214b3cf8c82a00`. Main delivery remains incomplete.
Hosted comparable reduction and canonical ranking provenance remain unresolved;
this local test/coverage run establishes neither.

The prepared corrected PR body is `/tmp/issue-3956-reconciled-pr-body.md`.
Its two inspection tasks are checked and its merge task is unchecked; the denied
remote update remains pending. Staging only the Node test, authoritative record
and new proof failed with exit 128: `.git/index.lock` cannot be created on the
read-only filesystem. Changes remain uncommitted for the runner; no push occurred.
No Python files changed, so the Python pre-commit formatting gate does not apply
to this round's edits. #4518 and #4401 were both read as open, `draft=false`.
