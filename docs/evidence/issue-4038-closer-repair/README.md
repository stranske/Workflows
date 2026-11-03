# Runner-core acceptance evidence

Check date: 2026-11-02 (America/Chicago). Mutation-proof base: main
`c4633a95058d927c309dc7d666ff1d8dc85c2cc3`, containing merged #4039
(`cbb9e35489cbff054f26a8b8f646cf4080baee7a`).
Before publication the provisioned branch was rebased onto fresh main
`3e513d30e1b11b30bd6a2fdc224adbca97d85930`; that intervening commit changes
neither runner production source nor its tests.

Outcome 1: all 30 cases added by #4039 fail their mapped semantic mutation and
pass after restoration. Command:
`/opt/anaconda3/bin/python3 /private/tmp/workflows-4038-mutations.py`.
The one-run harness was generated from the exact replacements below and the
AST difference between #4039's parent and merge test files; it is scratch data,
not a new production/test dependency. Its observed terminal output was:

```text
MUTATION_CASES_PASS=30/30
PRODUCTION_RESTORED=true
```

The stop rule recorded before mutation was three unsuccessful attempts at one
step or 60 minutes. The harness's first preflight detected an incorrectly bounded
replacement; no mutation ran before that preflight was corrected. Every actual
behavioral control then failed as intended and passed on restoration.

No explicitly selected repository virtual environment exists in this checkout.
The owner-selected fallback `/opt/anaconda3/bin/python3` is Python 3.12.2.
This differs from hosted Gate's Python 3.13/3.14; hosted CI is recorded separately.

## Focused validation and scope

```text
$ /opt/anaconda3/bin/python3 -m pytest tests/scripts/test_runner_lib.py -q
303 passed in 0.99s

$ /opt/anaconda3/bin/python3 -m pytest tests/scripts/test_runner_lib.py -q
303 passed in 1.78s
# Second run: after all mutations were restored.
```

AST inventory: 21 test functions added by #4039, expanding to 30 collected cases.
All 21 functions remain AST-identical to their merged versions on current main.
No tests were padded, replaced, removed, or strengthened. No production fix was
necessary. The repair retains only this evidence document.

The mutation source SHA-256 before and after every control is
`cffb417b93c65e789fe7bf433a0cfadc376b536e98826dbcb977e8f4f1a6c184`.
The historical parent and merge core source are identical to each other, with
SHA-256 `2074782d0b91207d27683a7f3d1d9f6e97327dce757e473523469ff79e36fec5`.
Current main includes later production work; the mutation proof exercises current
main, while the coverage attribution below uses the historical pair explicitly.

## Complete mutation definitions

Each replacement was temporary and independently restored. For a shared
mutation, each mapped case was invoked separately and actually failed. No import,
collection, syntax, or fixture failure is counted. `DID NOT RAISE` is pytest's
failed expected-exception assertion.

| Control | Temporary behavior change in `scripts/runner_lib/core.py` |
|---|---|
| copy-files | `_materialize_single_checkout_plan`: replace `shutil.copy2(src, dst)` with `dst.write_text("mutant", encoding="utf-8")`. |
| receipt-create | `PrCommentRunnerStorage.write_completion`: final create method `POST` → `PATCH`. |
| receipt-boundary | `PrCommentRunnerStorage.write_completion`: reservation-boundary `break` → `continue`, allowing an older receipt to be patched. |
| receipt-idempotence | `PrCommentRunnerStorage.write_completion`: `if existing == receipt:` → `if False:`, forcing an unnecessary write. |
| receipt-replacement | `PrCommentRunnerStorage.write_completion`: replacement method `PATCH` → `POST`. |
| github-outputs | `_write_github_output`: replace formatted key/value writes with `handle.write("mutant=true\n")`. |
| authority-cli-status | `_cmd_finalize_authority_challenge`: invert the decision-dependent return status. |
| completion-cli-success | `_cmd_record_completion`: insert `result = dataclasses.replace(result, success=True)` immediately before `record_completion`. |
| unknown-reference | `materialize_reference_packs`: return `None` instead of raising for an unknown named pack. |
| receipt-selection | `PrCommentRunnerStorage.read_record`: return the pending reservation instead of the matching completion receipt. |
| invalid-authority | `PrCommentRunnerStorage.read_record`: return the malformed reservation instead of raising `Invalid authoritative runner reservation`. |
| fallback-read | `FallbackRunnerStorage.read_record`: return `None` instead of reading the fallback after an empty primary read. |
| graphql-shape | `PrCommentRunnerStorage._iter_comments`: return before validating the GraphQL comments connection, suppressing both malformed-shape errors. |
| unstable-id | `PrCommentRunnerStorage._iter_comments`: return instead of raising at the invalid `raw_id` guard. |
| trusted-marker | `PrCommentRunnerStorage._find_comment`: disable the untrusted-author skip. |
| helper-json | `_authority_challenge_command`: return `None` instead of the decoded JSON dictionary. |
| nested-errors | `_extract_text_from_json_event`: disable extraction of content lists, including nested error text. |
| release-identity | `release_authority_challenge`: remove the reservation-key mismatch guard. |
| storage-factory | `_storage_from_name`: select the repo-variable backend for `pr-comment`. |
| finalize-grant | `finalize_authority_challenge`: return `should_dispatch=False` for an otherwise valid granted reservation. |
| helper-exception | `_authority_challenge_command`: replace the OSError diagnostic with `warning: mutant helper failure: OSError`. |
| fallback-exception | `FallbackRunnerStorage.read_record`: return `None` after a primary read exception instead of reading fallback. |
| appendix | `assemble_prompt`: disable the keepalive task-appendix branch. |
| module-context | `_load_orchestrator_skill_module`: replace the required missing-context error text with `mutant module context`. |

## Complete node / failure / restoration matrix

Every command below was executed once under its mapped mutation (exit 1), then
executed again after byte-for-byte restoration (exit 0). Failure excerpts and
pytest terminal summaries are copied from actual stdout/stderr. Full collected
parameter IDs are retained, including spaces. The command is identical for the
RED and GREEN invocation; only the temporary production mutation differs.

### 01. copy-files

```text
$ /opt/anaconda3/bin/python3 -m pytest 'tests/scripts/test_runner_lib.py::test_materialize_orchestrator_skill_copies_direct_checkout_plan[main]' -q
RED (exit 1): AssertionError: assert 'mutant' == 'readme'
FAILED tests/scripts/test_runner_lib.py::test_materialize_orchestrator_skill_copies_direct_checkout_plan[main]
1 failed in 0.50s
RESTORED (exit 0): 1 passed in 0.41s
```

### 02. copy-files

```text
$ /opt/anaconda3/bin/python3 -m pytest 'tests/scripts/test_runner_lib.py::test_materialize_orchestrator_skill_copies_direct_checkout_plan[aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa]' -q
RED (exit 1): AssertionError: assert 'mutant' == 'readme'
FAILED tests/scripts/test_runner_lib.py::test_materialize_orchestrator_skill_copies_direct_checkout_plan[aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa]
1 failed in 0.50s
RESTORED (exit 0): 1 passed in 0.38s
```

### 03. receipt-create

```text
$ /opt/anaconda3/bin/python3 -m pytest 'tests/scripts/test_runner_lib.py::test_pr_comment_completion_receipt_is_idempotent_and_cannot_cross_reservations[none]' -q
RED (exit 1): AssertionError: assert ('PATCH', '/r.../42/comments') == ('POST', '/re.../42/comments')
FAILED tests/scripts/test_runner_lib.py::test_pr_comment_completion_receipt_is_idempotent_and_cannot_cross_reservations[none]
1 failed in 0.43s
RESTORED (exit 0): 1 passed in 0.29s
```

### 04. receipt-boundary

```text
$ /opt/anaconda3/bin/python3 -m pytest 'tests/scripts/test_runner_lib.py::test_pr_comment_completion_receipt_is_idempotent_and_cannot_cross_reservations[newer-reservation]' -q
RED (exit 1): AssertionError: assert ('PATCH', '/r...s/comments/1') == ('POST', '/re.../42/comments')
FAILED tests/scripts/test_runner_lib.py::test_pr_comment_completion_receipt_is_idempotent_and_cannot_cross_reservations[newer-reservation]
1 failed in 0.45s
RESTORED (exit 0): 1 passed in 0.45s
```

### 05. receipt-idempotence

```text
$ /opt/anaconda3/bin/python3 -m pytest 'tests/scripts/test_runner_lib.py::test_pr_comment_completion_receipt_is_idempotent_and_cannot_cross_reservations[same]' -q
RED (exit 1): AssertionError: assert [('PATCH', '/...EifQ== -->'})] == []
FAILED tests/scripts/test_runner_lib.py::test_pr_comment_completion_receipt_is_idempotent_and_cannot_cross_reservations[same]
1 failed in 0.38s
RESTORED (exit 0): 1 passed in 0.31s
```

### 06. receipt-replacement

```text
$ /opt/anaconda3/bin/python3 -m pytest 'tests/scripts/test_runner_lib.py::test_pr_comment_completion_receipt_is_idempotent_and_cannot_cross_reservations[replace]' -q
RED (exit 1): AssertionError: assert ('POST', '/re...s/comments/1') == ('PATCH', '/r...s/comments/1')
FAILED tests/scripts/test_runner_lib.py::test_pr_comment_completion_receipt_is_idempotent_and_cannot_cross_reservations[replace]
1 failed in 0.47s
RESTORED (exit 0): 1 passed in 0.33s
```

### 07. github-outputs

```text
$ /opt/anaconda3/bin/python3 -m pytest tests/scripts/test_runner_lib.py::test_assemble_and_parse_cli_write_expected_github_outputs -q
RED (exit 1): AssertionError: assert 'file=codex-prompt-42.md' in 'mutant=true\nmutant=true\nmutant=true\nmutant=true\nmutant=true\nmutant=true\nmutant=true\nmutant=true\nmutant=true\n'
FAILED tests/scripts/test_runner_lib.py::test_assemble_and_parse_cli_write_expected_github_outputs
1 failed in 0.46s
RESTORED (exit 0): 1 passed in 0.55s
```

### 08. authority-cli-status

```text
$ /opt/anaconda3/bin/python3 -m pytest 'tests/scripts/test_runner_lib.py::test_authority_challenge_cli_reports_decision[True]' -q
RED (exit 1): AssertionError: assert 1 == 0
FAILED tests/scripts/test_runner_lib.py::test_authority_challenge_cli_reports_decision[True]
1 failed in 0.70s
RESTORED (exit 0): 1 passed in 0.60s
```

### 09. authority-cli-status

```text
$ /opt/anaconda3/bin/python3 -m pytest 'tests/scripts/test_runner_lib.py::test_authority_challenge_cli_reports_decision[False]' -q
RED (exit 1): AssertionError: assert 0 == 1
FAILED tests/scripts/test_runner_lib.py::test_authority_challenge_cli_reports_decision[False]
1 failed in 0.66s
RESTORED (exit 0): 1 passed in 0.48s
```

### 10. completion-cli-success

```text
$ /opt/anaconda3/bin/python3 -m pytest 'tests/scripts/test_runner_lib.py::test_autofix_completion_cli_honors_exit_code_and_evidence_cli_outputs[autofix]' -q
RED (exit 1): AssertionError: assert True is False
FAILED tests/scripts/test_runner_lib.py::test_autofix_completion_cli_honors_exit_code_and_evidence_cli_outputs[autofix]
1 failed in 2.65s
RESTORED (exit 0): 1 passed in 2.08s
```

### 11. completion-cli-success

```text
$ /opt/anaconda3/bin/python3 -m pytest 'tests/scripts/test_runner_lib.py::test_autofix_completion_cli_honors_exit_code_and_evidence_cli_outputs[codex]' -q
RED (exit 1): AssertionError: assert True is False
FAILED tests/scripts/test_runner_lib.py::test_autofix_completion_cli_honors_exit_code_and_evidence_cli_outputs[codex]
1 failed in 0.77s
RESTORED (exit 0): 1 passed in 0.60s
```

### 12. unknown-reference

```text
$ /opt/anaconda3/bin/python3 -m pytest tests/scripts/test_runner_lib.py::test_reference_pack_materialization_handles_missing_config_and_unknown_pack -q
RED (exit 1): Failed: DID NOT RAISE ValueError
FAILED tests/scripts/test_runner_lib.py::test_reference_pack_materialization_handles_missing_config_and_unknown_pack
1 failed in 0.81s
RESTORED (exit 0): 1 passed in 0.47s
```

### 13. receipt-selection

```text
$ /opt/anaconda3/bin/python3 -m pytest tests/scripts/test_runner_lib.py::test_pr_comment_storage_returns_only_receipt_for_current_reservation -q
RED (exit 1): AssertionError: assert {'pr_number':...s': 'pending'} == {'provider': ...: 'attempt-2'}
FAILED tests/scripts/test_runner_lib.py::test_pr_comment_storage_returns_only_receipt_for_current_reservation
1 failed in 0.71s
RESTORED (exit 0): 1 passed in 0.55s
```

### 14. invalid-authority

```text
$ /opt/anaconda3/bin/python3 -m pytest tests/scripts/test_runner_lib.py::test_pr_comment_storage_rejects_malformed_authoritative_reservation -q
RED (exit 1): Failed: DID NOT RAISE RuntimeError
FAILED tests/scripts/test_runner_lib.py::test_pr_comment_storage_rejects_malformed_authoritative_reservation
1 failed in 0.53s
RESTORED (exit 0): 1 passed in 0.46s
```

### 15. fallback-read

```text
$ /opt/anaconda3/bin/python3 -m pytest tests/scripts/test_runner_lib.py::test_fallback_storage_preserves_primary_and_uses_legacy_only_when_needed -q
RED (exit 1): AssertionError: assert None == {'status': 'legacy'}
FAILED tests/scripts/test_runner_lib.py::test_fallback_storage_preserves_primary_and_uses_legacy_only_when_needed
1 failed in 0.68s
RESTORED (exit 0): 1 passed in 0.39s
```

### 16. graphql-shape

```text
$ /opt/anaconda3/bin/python3 -m pytest 'tests/scripts/test_runner_lib.py::test_pr_comment_storage_fails_closed_on_invalid_graphql_shapes[response0-Missing runner comments]' -q
RED (exit 1): Failed: DID NOT RAISE RuntimeError
FAILED tests/scripts/test_runner_lib.py::test_pr_comment_storage_fails_closed_on_invalid_graphql_shapes[response0-Missing runner comments]
1 failed in 0.70s
RESTORED (exit 0): 1 passed in 0.61s
```

### 17. graphql-shape

```text
$ /opt/anaconda3/bin/python3 -m pytest 'tests/scripts/test_runner_lib.py::test_pr_comment_storage_fails_closed_on_invalid_graphql_shapes[response1-Invalid runner comments]' -q
RED (exit 1): Failed: DID NOT RAISE RuntimeError
FAILED tests/scripts/test_runner_lib.py::test_pr_comment_storage_fails_closed_on_invalid_graphql_shapes[response1-Invalid runner comments]
1 failed in 0.79s
RESTORED (exit 0): 1 passed in 0.48s
```

### 18. unstable-id

```text
$ /opt/anaconda3/bin/python3 -m pytest 'tests/scripts/test_runner_lib.py::test_pr_comment_storage_rejects_unstable_comment_ids[True]' -q
RED (exit 1): Failed: DID NOT RAISE RuntimeError
FAILED tests/scripts/test_runner_lib.py::test_pr_comment_storage_rejects_unstable_comment_ids[True]
1 failed in 0.54s
RESTORED (exit 0): 1 passed in 0.45s
```

### 19. unstable-id

```text
$ /opt/anaconda3/bin/python3 -m pytest 'tests/scripts/test_runner_lib.py::test_pr_comment_storage_rejects_unstable_comment_ids[0]' -q
RED (exit 1): Failed: DID NOT RAISE RuntimeError
FAILED tests/scripts/test_runner_lib.py::test_pr_comment_storage_rejects_unstable_comment_ids[0]
1 failed in 0.60s
RESTORED (exit 0): 1 passed in 0.36s
```

### 20. unstable-id

```text
$ /opt/anaconda3/bin/python3 -m pytest 'tests/scripts/test_runner_lib.py::test_pr_comment_storage_rejects_unstable_comment_ids[not-a-number]' -q
RED (exit 1): Failed: DID NOT RAISE RuntimeError
FAILED tests/scripts/test_runner_lib.py::test_pr_comment_storage_rejects_unstable_comment_ids[not-a-number]
1 failed in 0.55s
RESTORED (exit 0): 1 passed in 0.40s
```

### 21. trusted-marker

```text
$ /opt/anaconda3/bin/python3 -m pytest tests/scripts/test_runner_lib.py::test_pr_comment_find_and_write_record_use_trusted_marker_only -q
RED (exit 1): AssertionError: assert {'id': 1, 'bo... 'untrusted'}} == {'id': 2, 'bo...ZGV4In0= -->'}
FAILED tests/scripts/test_runner_lib.py::test_pr_comment_find_and_write_record_use_trusted_marker_only
1 failed in 0.48s
RESTORED (exit 0): 1 passed in 0.55s
```

### 22. helper-json

```text
$ /opt/anaconda3/bin/python3 -m pytest tests/scripts/test_runner_lib.py::test_authority_challenge_helper_accepts_only_current_dispatch_and_valid_json -q
RED (exit 1): AssertionError: assert None == {'prepared': True}
FAILED tests/scripts/test_runner_lib.py::test_authority_challenge_helper_accepts_only_current_dispatch_and_valid_json
1 failed in 0.66s
RESTORED (exit 0): 1 passed in 0.55s
```

### 23. nested-errors

```text
$ /opt/anaconda3/bin/python3 -m pytest tests/scripts/test_runner_lib.py::test_parse_runner_output_collects_content_chunks_and_nested_errors -q
RED (exit 1): assert '{"error": {"...pe": "error"}' == 'nested failure'
FAILED tests/scripts/test_runner_lib.py::test_parse_runner_output_collects_content_chunks_and_nested_errors
1 failed in 0.34s
RESTORED (exit 0): 1 passed in 0.41s
```

### 24. release-identity

```text
$ /opt/anaconda3/bin/python3 -m pytest tests/scripts/test_runner_lib.py::test_authority_release_terminalizes_only_matching_pending_reservation -q
RED (exit 1): AssertionError: assert True is False
FAILED tests/scripts/test_runner_lib.py::test_authority_release_terminalizes_only_matching_pending_reservation
1 failed in 0.83s
RESTORED (exit 0): 1 passed in 0.49s
```

### 25. storage-factory

```text
$ /opt/anaconda3/bin/python3 -m pytest tests/scripts/test_runner_lib.py::test_storage_factory_and_timestamp_helpers_preserve_backend_and_utc_contract -q
RED (exit 1): AssertionError: assert <tests.scripts.test_runner_lib.MemoryRunnerStorage object at 0x113671fd0> is <tests.scripts.test_runner_lib.MemoryRunnerStorage object at 0x113671eb0>
FAILED tests/scripts/test_runner_lib.py::test_storage_factory_and_timestamp_helpers_preserve_backend_and_utc_contract
1 failed in 0.67s
RESTORED (exit 0): 1 passed in 0.54s
```

### 26. finalize-grant

```text
$ /opt/anaconda3/bin/python3 -m pytest tests/scripts/test_runner_lib.py::test_authority_finalize_requires_auto_storage_grant_and_matching_reservation -q
RED (exit 1): AssertionError: assert False
FAILED tests/scripts/test_runner_lib.py::test_authority_finalize_requires_auto_storage_grant_and_matching_reservation
1 failed in 0.74s
RESTORED (exit 0): 1 passed in 0.62s
```

### 27. helper-exception

```text
$ /opt/anaconda3/bin/python3 -m pytest tests/scripts/test_runner_lib.py::test_authority_helper_rejects_wrong_context_and_helper_launch_failure -q
RED (exit 1): AssertionError: assert 'helper unavailable: OSError' in 'warning: mutant helper failure: OSError\n'
FAILED tests/scripts/test_runner_lib.py::test_authority_helper_rejects_wrong_context_and_helper_launch_failure
1 failed in 0.72s
RESTORED (exit 0): 1 passed in 0.44s
```

### 28. fallback-exception

```text
$ /opt/anaconda3/bin/python3 -m pytest tests/scripts/test_runner_lib.py::test_fallback_storage_uses_legacy_record_when_primary_read_fails -q
RED (exit 1): AssertionError: assert None == {'status': 'fallback'}
FAILED tests/scripts/test_runner_lib.py::test_fallback_storage_uses_legacy_record_when_primary_read_fails
1 failed in 0.96s
RESTORED (exit 0): 1 passed in 0.44s
```

### 29. appendix

```text
$ /opt/anaconda3/bin/python3 -m pytest tests/scripts/test_runner_lib.py::test_assemble_prompt_materializes_references_and_uses_keepalive_appendix -q
RED (exit 1): AssertionError: assert 'current tasks' in 'base\n\n## Repository Guidance\nrepository guidance\n\n## Reference Packs\nreferences\n'
FAILED tests/scripts/test_runner_lib.py::test_assemble_prompt_materializes_references_and_uses_keepalive_appendix
1 failed in 0.60s
RESTORED (exit 0): 1 passed in 0.54s
```

### 30. module-context

```text
$ /opt/anaconda3/bin/python3 -m pytest tests/scripts/test_runner_lib.py::test_prompt_and_context_module_errors_are_explicit -q
RED (exit 1): AssertionError: Regex pattern did not match.
FAILED tests/scripts/test_runner_lib.py::test_prompt_and_context_module_errors_are_explicit
1 failed in 1.21s
RESTORED (exit 0): 1 passed in 1.03s
```

## Gate configuration and historical hosted corroboration

The [Gate at #4039's merge](https://github.com/stranske/Workflows/blob/cbb9e35489cbff054f26a8b8f646cf4080baee7a/.github/workflows/pr-00-gate.yml)
calls the [same-commit reusable Python workflow](https://github.com/stranske/Workflows/blob/cbb9e35489cbff054f26a8b8f646cf4080baee7a/.github/workflows/reusable-10-ci-python.yml),
with Python 3.13 and 3.14, four xdist workers, `--dist=loadgroup`, and
`-m 'not quarantine and not slow'`. There is no explicit test-file argument:
`pyproject.toml` selects both `tests` and `.github/scripts/__tests__`.
The reusable workflow adds `--junitxml`, `--cov`, `--cov-config=pyproject.toml`,
and XML, terminal-missing, and JSON coverage reports. The historical config
sets `branch=true`, source `scripts`, `tools`, `src`, and the repository's
existing omissions; no threshold, marker, source, or exclusion was changed.
The workflow's transient collection/resource observer records metrics and does
not select tests; local reproduction omits that observer and runner caches.

Historical artifacts were checked again on 2026-11-02. Both run artifact lists
are empty, and the baseline artifact ID returns HTTP 404. The links below retain
the original identifiers, but **do not claim that deleted artifacts remain
available**. The retained job logs still expose the coverage table and passing
pytest summaries:

| Historical CI | Head | Missing statements | Missing branches | Total missing | Blended coverage |
|---|---|---:|---:|---:|---:|
| [Baseline Gate 39033565916](https://github.com/stranske/Workflows/actions/runs/39033565916/job/117399103785) | `2304df7633bca2cd2d8a251010090ce6433bdd2d` | 209 | 120 | 329 | 80.00% |
| [Final #4039 Gate, Python 3.13](https://github.com/stranske/Workflows/actions/runs/39079350563/job/117533108968) | `48fa8efc91f34dfde5b024bc93e3d42365fc4fdf` | 73 | 65 | 138 | 91.61% |
| [Final #4039 Gate, Python 3.14](https://github.com/stranske/Workflows/actions/runs/39079350563/job/117533108944) | same | 73 | 65 | 138 | 91.61% |

```text
Baseline Python 3.13: 50980 passed, 25 skipped, 3 xfailed in 610.90s
Final Python 3.13:    51156 passed, 26 skipped, 3 xfailed in 512.52s
Final Python 3.14:    51156 passed, 26 skipped, 3 xfailed in 485.15s
```

The logs report 1,193 statements and 452 branches for `core.py`. The terminal
`BrPart` column (70 before, 57 after) is *partially covered branches*, not missing
branches. Because the retained coverage percentages have two decimals, the
missing-branch counts can be uniquely recovered: among integers 0..452, only
120 satisfies `round(100*(1645-209-b)/1645, 2) == 80.00`, and only 65 satisfies
`round(100*(1645-73-b)/1645, 2) == 91.61`. These agree with the counts originally
recorded in #4039's body. The corroborated historical difference is 191 units;
this historical baseline is **not the merge parent**, so it is not used as the
repair's direct parent/merge attribution.

Original artifact links (currently unavailable):
[baseline 12101546514](https://github.com/stranske/Workflows/actions/runs/39033565916/artifacts/12101546514),
[final 3.13 12118915026](https://github.com/stranske/Workflows/actions/runs/39079350563/artifacts/12118915026),
[final 3.14 12118168803](https://github.com/stranske/Workflows/actions/runs/39079350563/artifacts/12118168803).

## Target-ranking provenance and limits

[The source issue](https://github.com/stranske/Workflows/issues/4038) records the
actual dispatched order: `scripts/runner_lib/core.py` is target 1, with 12
escaped-defect signals, churn 17, and 329 uncovered statements plus branches.
It explicitly orders escaped-defect priority first, churn second, uncovered mass
last. This is the historical selection receipt, not a ranking inferred from file
size or regenerated against today's main.

Read-only inspection on 2026-11-02 corroborated the routing implementation:
`~/.codex/orchestrator/coverage-campaign/v17/coverage-autopilot.py::rank_targets`
invokes `escaped_defect_priority.py --repo <clone> --coverage-json <payload>
--limit <limit> --json`, retains its order, and bundles eligible targets without
re-sorting them. The [ranker's source](https://github.com/stranske/Orchestrator/blob/main/escaped_defect_priority.py)
uses lexicographic tiers and describes the first tier as a git fix/revert proxy.
Thus 12 signals are not proof of 12 independently confirmed escaped defects.
The original complete ranker JSON was not recovered; the issue supplies the
selected row and order, while the current source corroborates the algorithm.

Coverage is an execution metric. A failing semantic mutation establishes
sensitivity to that mapped regression, not exhaustive correctness of every
assertion or all possible mutations. These are isolated unit/CLI tests with
stubbed APIs/helpers, not live GitHub storage or authority transactions.
No tests were added merely to move 171 toward 180. Local focused coverage and
whole-Gate coverage must not be substituted for one another.
