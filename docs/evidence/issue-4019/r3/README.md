# Issue 4019 closer repair r3: finish the ranked target list

Baseline and stop rule were recorded first in `acceptance.md`.

## Ranking and target selection

The issue's ranking comes from Orchestrator `coverage-autopilot.py`: escaped-defect signals, then churn, then
uncovered mass. Its order is aggregate_agent_metrics (16 signals, churn 45), check_consumer_sync_drift
(6, 14), then llm_provider (3, 3). This repository has no implementation of that ranking
(`docs/reference/coverage-gap-analysis.md` is guidance only). The issue forbids files outside the three
targets, so no other targets were selected. All three are low-risk test-only surfaces with no
network access: provider clients are faked through `sys.modules` and `patch`.

## Counts (hosted Gate, Python 3.14 artifact only, never summed with 3.13)

| Target | Round base 41557902073 | After PR 4406 (41668857273) | Historical #4431 parent (41717668636) |
| --- | ---: | ---: | ---: |
| scripts/aggregate_agent_metrics.py | 0 + 3 | 0 + 3 | 0 + 0 |
| scripts/check_consumer_sync_drift.py | 0 + 0 | 0 + 0 | 0 + 0 |
| tools/llm_provider.py | 77 + 27 | 54 + 16 | 3 + 0 |
| **TARGET_MISSING** | **107** | **73** | **3** |

Missing lines + missing branches. Printed by `target_missing.py` over each run's `gate-coverage-3.14-1`
`runtimes/3.14/coverage.json`. See `baseline-41668857273.txt` and `head-41717668636.txt`.

### Why "about 180" is not reachable, by target

- aggregate_agent_metrics: the issue body says 6 units, but the round base had 3, all now covered.
- check_consumer_sync_drift: the issue body says 79, but the round base had 0. Earlier work had already
  covered it before this round began, so there is nothing left to add.
- llm_provider: 104 at the round base. Everything is covered except 3 lines: the `pass` bodies of the
  abstract `name`, `is_available` and `analyze_completion` methods (265, 270, 292). They have no behavior.
  Covering them would only call `super()` from a test, which is padding. They were not excluded from coverage.

So the whole list held 107 units. The round removed 104 of them (3 + 0 + 101), and the list is exhausted.

## Real bug fixed (one word in `tools/llm_provider.py`)

`_supports_quality_context` logs "supports_quality_context raised ..., falling back to signature" when a
provider's helper raises. It then hit `if supports is not None: return bool(supports)`, and a bound method
is always truthy, so it returned True without checking the signature. As a result, a legacy provider with a
raising helper was reported as quality-context capable. That affects `get_quality_context_support_table`
and the codex_session_analyzer dispatch. Changing `if` to `elif` makes the logged fallback happen.
`bug-supports-quality-context-before-fix.txt` shows the new test failing on unmodified main source
(`assert True is False`, exit 1). Mutation 09 re-breaks it after the fix.

## Break-and-revert

`mutate.py` runs 27 mutations over 24 test functions (3 in aggregate, 21 in provider); some tests
get several mutations. Each mutation applies the exact replacement, runs the one node (exit 1, named
FAILED), restores the original bytes (sha256 checked), and reruns it (exit 0). Results are in
`mutations/mutation-receipts.json`, and the full output is in `mutations/NN-red.txt` and `NN-green.txt`.
The first `E` line of each red run shows the asserted behavior breaking; no red run is a collection error.

## Validation

- Required three-file pytest: `required-tests.txt` (268 passed, exit 0).
- Gate's pytest flags restricted to the three files: `focused-gate-invocation.txt` (268 passed, exit 0).
  This is diagnostic only. Its 15 extra provider lines (73-74, 220-224, 1019-1023, 1044) are covered by
  other test files in the whole-suite run.
- black 26.10.1 `--line-length 100` and ruff: no changes, all checks passed.
- The full suite runs only in hosted CI: 41717668636.

## Hosted CI

- Gate 41717668636 on `f485bbc25`: success. Python 3.14 job 126202357345 and Python 3.13 job 126202357499
  both ran the full pytest suite and passed. Its 3.14 coverage artifact prints `TARGET_MISSING 3`. The
  repository total moves from 63,040 to 63,110 covered units out of 69,241 (91.04% to 91.15%), the same
  denominator as the baseline.
- Gate 41714904528 on `a28894a1f` (attempt 1) ran pytest green on both runtimes, but lint failed on this
  directory's own helper scripts. The fix in `f485bbc25` is formatting only: no test or production change.
- The historical #4431 evidence commit added only these evidence numbers; this does not validate later heads.


## #4433 integration on current main

#4495 already delivered the raising-helper fix in both provider copies and
its regression; those are retained. This integration carries the missing
#4431 tests/evidence from `69e5b6d6cd3fb154be29890f2ae212772de8ce45`, fixes
the mutation driver and environment isolation, and adds driver regressions.
See `acceptance-integration.md` for current provenance and acceptance status.
All validation/counts above describe historical #4431 runs. Final-head hosted
Python 3.13/3.14 and raw coverage are PENDING, as are merge/main ancestry and
delivered-revision focused pytest. New receipts use `integration-rerun/mutations/` (executed on the post-#4495 integrated
tree `c1f18728c6b215fa7a66353b311fa12277074437` / cherry-pick `7ba92707`, where e.g.
`04-red.txt` reports `tests/tools/test_llm_provider.py:2178`);
the `mutations/` receipts and transcripts from #4431 candidate head
`69e5b6d6cd3fb154be29890f2ae212772de8ce45` (where `04-red.txt` reports
`tests/tools/test_llm_provider.py:2154` before #4495's 24-line regression addition)
were modified only to add `"revision": "69e5b6d6cd3fb154be29890f2ae212772de8ce45"` in
`mutation-receipts.json` and prepend `# revision: 69e5b6d6cd3fb154be29890f2ae212772de8ce45`
to each `NN-red.txt` and `NN-green.txt` transcript, while preserving all original
`sha256_before`/`sha256_restored` digests, exit codes, and transcript bodies.
No summary percentage substitutes
for separately identified raw runtime coverage or explicit residual lists.


The actual mutation-table function count is 24 (3 aggregate, 21 provider);
this corrects the historical 21/18 wording while retaining the candidate
receipt digests and output bodies described above. Review dispositions and bounded follow-ups are recorded in
`integration-rerun/review-dispositions.md`. The final immutable head, hosted
runs/raw artifact identities, merge SHA, and main ancestry are maintained in
the acceptance section of [integration PR #4516](https://github.com/stranske/Workflows/pull/4516).


The integrated-tree hosted checkpoint now measures TARGET_MISSING=3 on
`c4c91e4c91e3860c3519eb8bc61c7943b7cd8c5b` (Gate 42335283865): both Python
runtimes passed; 3.14 raw TOTAL=63868/70054, summary=92.60%, residual provider
lines [265,270,292], branches []; 3.13 has no coverage JSON. See the final
section of `acceptance-integration.md` and the distinct raw-artifact manifests.
That is a checkpoint before this documentation reconciliation. Final-head
confirmation and delivered-main acceptance are recorded in
[PR #4516](https://github.com/stranske/Workflows/pull/4516), not inferred here.
