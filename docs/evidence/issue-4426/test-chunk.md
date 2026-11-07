# Issue #4426 first test chunk

Checked 2026-11-06. Selection uses the regenerated current ranking in
`ranking.md`. Rank 1 is `scripts/langchain/pr_verifier.py` (escaped-defect
weight 62, churn 75, 273 missing statements and branches on Gate run
42250720123).

## Chunk

`expanded_comparison_verdict` in `scripts/langchain/pr_verifier.py`, lines
8857–8938. That range was the largest uncovered statement run in the Gate
`coverage.json`. The function admits a compare verdict from configured slot
identities or a signed semantic envelope. It does not construct a client or
call a provider.

Tests: `tests/scripts/test_pr_verifier_expanded_comparison_verdict.py`.

```bash
python3 -m pytest -q tests/scripts/test_pr_verifier_expanded_comparison_verdict.py --cov=scripts.langchain.pr_verifier --cov-branch --cov-report=json:/tmp/pr-verifier-chunk-cov.json -m "not slow"
```

Result on 2026-11-06: 13 passed in 1.20s. That coverage JSON has no missing
statements and no missing branches on lines 8855–8938.

This is one logical chunk. It does not replace the original about-180
uncovered-statement-and-branch rule, and it does not claim that reduction.

## Targets not in this chunk

These files are not #3998 exclusions. Dead code and an external service that
cannot be faked are the only exclusion reasons in the recovered contract.
Inability to obtain a terminal receipt is not a reason used here. Each file
stays in regenerated order for a later chunk.

| Target | Current Gate units | Why this chunk did not take it |
| --- | ---: | --- |
| `scripts/sync_test_dependencies.py` | 6 | Rank 2. One missing statement and five missing branches. The reachable residue is smaller than the uncovered admission function, and escaped-defect weight 17 is below `pr_verifier.py`. |
| `tools/langchain_client.py` | 21 | Rank 3. Provider selection is already faked in `tests/tools/test_langchain_client.py`. It is a separate client-cache chunk, not an unfakeable service. |
| `scripts/langchain/task_validator.py` | 6 | Rank 4. Six units remain. They are ordinary validator branches, and they rank below the selected function. |
| `scripts/langchain/verifier_config.py` | 2 | Rank 5. Two units remain after the tests #4000 landed on main. The residue is smaller than this function. |
| `scripts/langchain/issue_pr_context.py` | 19 | Rank 6. Nineteen uncovered units, with escaped-defect weight 2, so the regenerated order places it last. The module parses local issue and pull-request context. |

Other uncovered regions inside `scripts/langchain/pr_verifier.py`, including
follow-up issue creation, live model invocation, and CLI `main`, are separate
chunks. This record does not call them dead or unfakeable.

## Follow-up symbol selection, 2026-11-07

Selected before editing: `_build_verifier_repair_callback`, specifically its nested
`_repair` response normalization and rejection at lines 8216–8219. The verified
final-head Gate job log in `final-head-gate.json` lists those statements as missing.
The selection uses those real missing statements; complete missing-branch arcs
and attributable round-wide accounting remain blocked on artifact recovery.
This small chunk advances task 2 without completing its approximately 180-unit
contract. All six targets retain their recorded ranking; the other five remain
pending, with no exclusion claimed. `_create_followup_issue` is not selected:
its feature switch currently always returns false, so re-enabling that switch
only in a test would not validate a production path. This is a symbol-level
selection decision, not an exclusion of `pr_verifier.py`.


## Chunk failure coverage, 2026-11-07

Selected symbol: `_evaluate_chunked`, in the highest-ranked target
`scripts/langchain/pr_verifier.py`. The added ranked remainder tests exercise
failed cross-file synthesis after successful assigned-file inspections, and
local prompt rejection for unavailable code or required evidence. They assert
review credit, conservative verdicts, preserved concrete findings, and zero
provider calls for rejected input. Provider invocation and local prompt
measurement are the test seams; chunk construction and aggregation run as-is.

Five parameter cases each have a named mutation failure and restored pass in
`chunk-failure-mutations.json`; reproduce with
`python docs/evidence/issue-4426/chunk-failure-mutation-driver.txt`.
The prior receipts and their source snapshots remain unchanged.

Against the same three-module chunk suite, the additions cover statements
6833, 6843, 6960 and 6961 and branch outcome 6832->6833. All five units appear
in the final-head Gate missing report. This is a local incremental gain of
five units under unchanged source and configuration, not the attributable
approximately 180-unit round-wide result. All six targets retain their
recorded disposition; none is excluded. Task 1 remains blocked on comparable
artifact recovery, and full task 2 acceptance remains unverified.


## Native slot and package admission, 2026-11-07

Selected before editing: `_semantic_slots_and_clients` and
`_semantic_package_prompt` in the highest-ranked target, `pr_verifier.py`.
Four added behavioral tests (12 parameter cases) check frozen native provider
and model identities, both SDKs' zero-retry requirement, paired SDK validation,
synthetic provenance, exact dependency bytes, assigned obligations and follow-up
chain depth. Only SDK preparation/contract discovery and prompt loading are
faked; the slot admission and package assembly execute unchanged.

Six mutations each produce named assertion failures and restored passes in
`native-slot-mutations.json`. Reproduce with
`python docs/evidence/issue-4426/native-slot-mutation-driver.txt`.
`native-slot-validation.json` and its two compressed coverage artifacts record
the same two-module command before/after the additions: 61/73 tests pass,
24 additional statements and ten branch outcomes are covered, and no previously
covered unit is lost. Four of those units are explicitly missing in the final
Gate log: statements 8454, 8463 and 8515, and arc 8464->8466.

The 34-unit local increment is separate from original-round attribution.
Source and coverage configuration are unchanged. The other five targets keep
their previous dispositions; none is excluded. Final artifact recovery,
comparable original-round execution and passing exact-head Gate results remain
required before the numerical contract can be marked complete.
