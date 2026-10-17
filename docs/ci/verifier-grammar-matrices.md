# Bounded verifier grammar regression matrices

Issue #3904 changes test design, not production verifier behavior or delivery gates.
The source base is `12cea89599a67c3004d1d469d669c2daa33dfd35`.

## Retained regression map

All 356 original test function names remain. Seventeen changed functions retain
their original assertion bodies; the product/component function retains its
classifier assertions and moves its real prompt/floor assertions to the explicitly
mapped `test_product_component_coordination_real_floor`. Its criterion builder is
shared, rather than copied. That integration matrix has 288 cases crossing
active/passive agent placement, mandatory/optional/prohibited governor, attached
availability, independent duty, destination, AND/OR, and destination order.

The adjacent prompt-coverage and overall-integration files are unchanged. Their
existing literal, unavailable, body, artifact, conjunction, and coverage-floor
boundary cases remain required. No test is skipped or moved to nightly.

`verifier-grammar-matrices.json` is the machine-readable map: original dimension
values and counts, full semantic dimensions, lexical interaction axes, retained
counts, and source base. The helper in the destination test file implements only
this small local case construction; it is not a new test runner or framework.

[`verifier-grammar-inventory.json`](verifier-grammar-inventory.json) inventories
every original named regression, including generated fixtures: original parameter
groups and their sizes, original counts, and retained counts. An original count
of zero identifies the added real-floor integration test. The 338 unchanged
functions retain every original combination, so no independence assumption or
semantic/lexical decomposition is applied to them. For the 18 bounded functions,
join on `function` with `verifier-grammar-matrices.json` for the explicit semantic
dimensions and lexical interactions. The two focused tests in
`tests/scripts/test_pr_verifier_grammar_inventory.py` check the inventory against
the actual decorators and verify that every declared semantic and lexical
projection has an emitted case. They enumerate only bounded witnesses, without
executing another grammar cross-product. Run them with:

```sh
python -m pytest tests/scripts/test_pr_verifier_grammar_inventory.py -q -m "not slow"
```

When intentionally changing parametrizations, update the retained inventory and
interaction map together and review any newly omitted interaction. This audit
does not establish equivalence of deleted joint lexical combinations or replace
the production mutation and branch/line comparisons below.

| Named regression | Old cases | Retained cases |
| --- | ---: | ---: |
| `test_participial_content_is_not_a_component_name` | 1536 | 304 |
| `test_product_chain_inherits_latest_explicit_governor_and_aspect` | 2304 | 960 |
| `test_product_coordination_preserves_recipients_and_explicit_governor_reset` | 1008 | 546 |
| `test_product_generation_uses_shared_delivery_operations` | 3312 | 450 |
| `test_product_component_coordination_preserves_bare_other_channel` | 11520 | 668 |
| `test_passive_delivery_agent_position_preserves_actor_and_floor` | 4608 | 732 |
| `test_passive_aliases_preserve_actor_options_and_actual_floor` | 3240 | 600 |
| `test_component_availability_preserves_bare_sibling_and_passive_actor` | 3888 | 1350 |
| `test_relative_checklist_delivery_reuses_negative_optional_governor` | 2700 | 335 |
| `test_attached_availability_relative_preserves_destination_or` | 4608 | 380 |
| `test_possession_auxiliary_cannot_make_supply_noun_a_delivery` | 6318 | 140 |
| `test_prohibition_polarity_is_clause_order_and_alias_symmetric` | 1620 | 600 |
| `test_negative_passive_coordination_respects_contrast` | 2025 | 225 |
| `test_active_perfect_elided_delivery_retains_actor_and_governor` | 10206 | 756 |
| `test_optional_review_predicate_cannot_suppress_elided_mandatory_delivery` | 2160 | 540 |
| `test_passive_product_storage_shared_review_destination` | 1008 | 189 |
| `test_common_proof_pronoun_reuses_shared_finite_destination_grammar` | 1728 | 648 |
| `test_qualified_common_proof_reuses_shared_governor_boundary` | 1920 | 512 |

The changed matrices fall from 65,709 to 9,935 cases. With the 288 explicitly
mapped full-integration cases, the destination file falls from 90,550 to 35,064
cases (55,486 fewer, 61.28%). The other 338 original functions retain their full
parametrizations. This count reduction is not a measured runtime speedup.

## What the decomposition preserves and does not prove

For each original Cartesian row, project its semantic coordinates onto a retained
core row, using the first value for lexical dimensions. Then, for each lexical
axis, project that axis and its declared interaction coordinates onto a retained
lexical row. All these witnesses must exist. The full semantic cross-product,
every original lexical value, and every declared lexical/semantic interaction
therefore remain inspectable without enumerating their joint Cartesian product.
This is a decomposition map, not a claim that every deleted tuple is equivalent.

Polarity, actor class, destination identity/order, AND/OR, condition attachment,
independent duties, aspect and agent position remain semantic axes where they
change the grammar. Lexical sweeps deliberately retain operation × voice ×
governor × destination, irregular participle × governor × contrast, adverb ×
position × governor, and availability predicate × actor × attachment interactions.
The manifest states each target's exact axes rather than relying on random or
pairwise sampling. Role, spelling, and marker combinations outside these explicit
spines are no longer exhaustive. A concrete regression requiring another joint
interaction must add a named case or expand that target's declared spine.

Full branch/line coverage comparison and causal production mutants are separate
checks. Equal aggregate coverage alone would not establish grammar equivalence.
Any lost production branch needs a specific retained regression or documented
justification before source acceptance; unresolved losses keep #3904 open.

## Collection and JUnit growth receipts

The existing reusable Python CI pytest step records selected node IDs on the
controller (including xdist) into `pytest-collection.json`. It reports total and
per-file selected collection counts, largest parametrized functions, and elapsed
startup/collection to the first complete worker collection. It does not run tests
twice, change their selection, or suppress failures. Pytest itself checks xdist
worker collection consistency.

The existing **Record CI summary** step stages that receipt beside each runtime's
JUnit/coverage payload and publishes `test_growth` in summary.json and the job
summary. JUnit timings are summed worker-seconds, explicitly distinct from wall
time. Reported JUnit case count can differ from collection (interruptions, setup
errors, or an early exit); missing/malformed receipts stay unknown and preserve
the real test outcome.

A function above 1,000 cases or file above 50,000 cases raises a nonblocking review
signal. Review the new semantic interaction, retained lexical axes, before/after
node counts, dominant JUnit cost and causal regression proof. A deliberate
exception needs that rationale in the PR; do not raise a timeout or remove gates.
The 1,350-case component-availability core is intentional: missing state, independent
duty, governor, availability attachment, order, conjunction, destination and voice
are retained jointly. Its signal remains visible rather than being hidden by a
special exemption. These are bounded review budgets, not arbitrary test-failure
thresholds or an authorization to relax existing coverage/security/merge checks.

## Reproduction and remaining acceptance

Use the application's selected Python 3.12+ environment, with repository test
requirements and pytest-cov/xdist installed. In this app the verified interpreter
is `/opt/anaconda3/bin/python3`; other installations should supply their selected
absolute executable. Use identical interpreters, dependency versions, four workers,
loadgroup scheduling, coverage configuration and commands for both source heads:

```sh
"$WF_PYTHON" -m pytest tests/scripts/test_pr_verifier_delivery_destinations.py tests/scripts/test_pr_verifier_prompt_coverage.py tests/scripts/test_pr_verifier_body_overall_integration.py -q -n 4 --dist loadgroup --cov --cov-config=pyproject.toml --cov-report=json:coverage.json --cov-report= --junitxml=pytest-junit.xml
"$WF_PYTHON" -m pytest --collect-only -q tests/scripts/test_pr_verifier_delivery_destinations.py tests/scripts/test_pr_verifier_prompt_coverage.py tests/scripts/test_pr_verifier_body_overall_integration.py
"$WF_PYTHON" -m pytest tests/workflows/test_ci_test_growth.py tests/workflows/test_reusable_ci_workflow.py -q
```

Retain the commands, source/test/config hashes, JUnit, coverage JSON and raw logs.
Compare executed lines and arcs in the unchanged production classifier/floor
functions, not just percentages. The private proof must return assertion RED
when `_required_evidence_channels` returns an empty set and when
`_apply_coverage_floor` returns the incoming PASS unchanged, followed by GREEN on
byte-identical source restoration. The latter uses the explicitly mapped real-floor
test, not merely a classifier expectation.

The before Gate is https://github.com/stranske/Workflows/actions/runs/38938420079
(dispatched against main for the verified base; verify the actual run head).
The implementation PR's required Gate supplies after evidence. Compare Python
3.12 and 3.13 separately using actual runner/worker/dependency/coverage settings,
scoped JUnit counts and costs, collection time, reporting and total job wall time.
The local baseline and candidate run concurrently, so their elapsed times are observational and not a controlled speedup measurement. A local run does not establish hosted performance. Do not close #3904 or claim a
sub-10-minute Gate until controlled hosted evidence supports that claim. If the
runtime target remains unmet, name the measured residual bottlenecks and gap.


### Collection and timing receipt integrity

The controller clears the previous collection receipt before pytest starts. It
publishes selected counts only after successful serial collection or matching
xdist worker collections without collection errors. Test failures retain valid
collection counts; collection/startup failures do not become complete receipts.
The always-run summary validates parsed receipt shapes before aggregation.
JUnit case counts survive invalid durations, while rankings remain explicitly
UNKNOWN until all durations are finite and nonnegative. Defused XML parsing
rejects entities. The reusable workflow embeds the source `junit_report` helper
so consumers require no new synced helper file; the tests enforce source parity.
Selftest installs pinned xdist and defusedxml for these actual workflow paths.

Focused gate: `python -m pytest tests/workflows/test_ci_test_growth.py -q -o addopts=`.
The tests execute the actual workflow Python/shell paths, including serial/xdist
collection errors, stale startup evidence, malformed JSON, invalid durations,
and entity rejection. The implementation PR retains RED/GREEN command output;
these controls do not replace the original matched coverage and hosted timing
acceptance for issue #3904.

## Controlled hosted comparison

`maint-88-verifier-runtime-comparison.yml` is a finite manual experiment for #3904,
not a new PR gate or recurring benchmark service. After normal review/merge, dispatch
it once from the reviewed harness commit. It runs Python 3.12 and 3.13 on standard
`ubuntu-latest` runners. Within each job, both arms share the exact interpreter,
installed dependency set, four loadgroup workers, markers, coverage configuration,
commands and runner. The common dependency lock is taken from candidate
`999ffe5fa00ac9c8ae8a807447f053277032b670`; baseline source is
`2f9eb2de718d1a561bce6fc0bff46fe8b9867905`. No moving merge ref or `main` supplies
measured source. The harness refuses unequal production verifier bytes or unequal
pytest/coverage configuration. This isolates the original test-design change under
a common candidate environment; it does not compare each historical installation.

No artifact or dependency cache restore runs. Each arm starts in a fresh source
archive with pytest cache disabled, bytecode writes disabled, and its own temporary
directory. OS page-cache effects are not controlled; Python 3.12 runs baseline first
and Python 3.13 runs candidate first. These are one pair per interpreter, not repeated
trials sufficient to estimate variability. Dependency installation is outside the
timed arms. This experiment therefore cannot claim that removing the former
423-second artifact-discovery stall caused a test-execution speedup.

The uploaded manifest records source commits/tree IDs, suite/source/configuration
hashes, dependency lock hash, reviewed workflow SHA/hash and harness hash. Results
retain actual package versions before/after both arms, exact commands, outer wall
time, JUnit elapsed and summed worker timings, raw consoles and branch coverage.
Startup/collection/reporting are included in outer wall time, not separately inferred.
Any pytest failure, environment drift, missing coverage, or lost executed verifier
line/branch fails the measurement job; no coverage threshold or required Gate is
changed. Retain and adjudicate losses rather than treating aggregate percentage
equality as equivalence. Passing this experiment does not establish all removed
lexical tuples equivalent, all required jobs under ten minutes, or closure of #3904.

Local checks before review:

```bash
python -m pytest tests/scripts/test_measure_verifier_runtime.py tests/workflows/test_workflow_naming.py -q
python scripts/measure_verifier_runtime.py prepare --output /tmp/issue3904-prepared-unique
```

The second command validates and hashes the actual immutable inputs without
executing the large suites. The real hosted pair runs only after the new workflow
is reviewed and available on the default branch. Rollback is to remove this manual
workflow and harness; production Gate/reusable CI have no dependency on either.

## Relative-presence cache locality

`test_component_relative_presence_preserves_parent_actual_floor` retains every
original Cartesian row and assertion: 648 cases, 2,592 classifier/options pairs,
and 10,368 real prompt/floor evaluations. The target and shared component-helper
argument lists and assertion bodies are unchanged. No semantic or lexical
integration combinations are omitted, and the 35,064-case inventory is unchanged.

Only xdist scheduling changes. Six non-missing parameter axes receive short,
family-specific `xdist_group` marks. Existing xdist 3.8 combines these marks into
324 distinct two-case work units. Each unit has one identical criterion across
`absent` and `unavailable` status, so both execute together on the same worker.
Each still crosses all four relative attachment strings and all four body/comment
presence sets. Every operation, voice, destination alias/direction, order,
conjunction and governor retains its original full product with both statuses.
The groups are exclusive to this family and do not serialize the whole family.
Serial execution also retains all original checks.

This exploits the existing process-local 512-entry pure-classifier LRU without
changing production code or cache capacity. Previously the two status blocks put
1,296 distinct attachment criteria between identical classifier inputs; cache
entries could expire before reuse. The paired cases share classifier results,
while still building and checking real evidence contexts for both missing states.
The optimization relies on the classifier's existing purity/cache contract;
missing status is an evidence input, never an acceptance-criterion input.

`tests/scripts/test_pr_verifier_relative_presence_groups.py` checks the actual
parameter marks form exactly 324 pairs with identical non-status coordinates,
that no other destination regression uses the family group namespace, and that
all 2,592 unique helper dispatches remain. The existing helper's four presence
states are also observed through the real floor for both missing statuses, with
all four body/comment pairs and their verdicts checked directly. This scheduling
change leaves production verifier bytes, runtime selection,
coverage configuration and required gates unchanged.

A matched sequential LOCAL Python 3.12.2 observation used four loadgroup workers,
standard repository markers/coverage configuration, JUnit and coverage JSON, with
only the optional rerunfailures plugin disabled. Before/after both passed all 648
cases: wall time was 75.598 / 60.668 seconds, summed JUnit worker time was
249.617 / 191.287 seconds, and child CPU time was 278.062 / 219.546 seconds.
Temporary read-only instrumentation on both runs recorded identical worker
collections and verified all 324 pairs stayed together. Candidate worker case
counts were 164, 162, 160 and 162. Executed production lines and arcs were
identical across all measured files. Source/config hashes, unchanged test-body
and signature AST hashes, raw logs, group/worker receipts, JUnit and coverage
JSON are retained in `/tmp/relative-floor-evidence-20261017` for local review.
This shared-Mac observation does not establish hosted speedup. Normal hosted
validation on the selected runtime matrix remains required. Merged PR #4016 sets
default CI to parallel Python 3.13/3.14 while retaining explicit 3.12 overrides.

Private required-channel-empty and coverage-floor-bypass mutations both failed
a retained assertion, then passed after restoring byte-identical production
source; their test/source hashes and logs are retained with the local receipts.

A second matched LOCAL observation used the selected default runtimes, the same
lockfile, four loadgroup workers and branch coverage. Archived baseline
`e33d5091255dcaa82ed748963d7935c473bc2bc1` and locality candidate
`f3960dd434be13bc1f57adc1e02bd0f6eb5765d0` ran sequentially:

| Runtime | Wall seconds before / after | Summed worker seconds before / after |
| --- | ---: | ---: |
| Python 3.13.13 | 16.370 / 14.555 | 28.857 / 22.513 |
| Python 3.14.3 | 12.158 / 10.489 | 19.258 / 13.496 |

All four runs passed 648 cases. Both candidates retained all 324 intact pairs
across four workers, identical original node IDs (apart from xdist group suffixes),
and identical executed production lines/arcs. Source, lockfile, package versions,
commands and raw receipts are recorded in
`/tmp/relative-floor-evidence-20261017/parity313-314/summary.json`.
These single-pair local observations do not establish a hosted speedup or a
sub-ten-minute full Gate. The immutable historical comparison is unchanged.


## Per-worker resource observations

The existing dynamic `ci_test_growth` observer also writes one compact,
atomic JSON record per pytest process into a fresh runner-temp directory.
`Record CI summary` validates these records after artifact staging clears the
restored runtime tree, then includes `pytest-resources.json` and
`summary.json.worker_resources` in the existing runtime artifact. Coverage-disabled
pytest runs retain resource observations too; missing, crashed or malformed
worker records remain `UNKNOWN`. These best-effort observations never change
pytest outcomes, collection receipts, coverage configuration, thresholds or gates.
`COMPLETE` means the process records are accounted for; unavailable context fields
remain null and do not establish causal acceptance.

Worker records contain the runtime, worker ID, actual `call` report count,
monotonic session elapsed time, and process SELF user/system CPU deltas.
The interval is pytest session start through session finish, including collection;
it is distinct from JUnit worker-seconds and from runner job wall time. Setup skips
have no call report. The controller is labeled separately; its forwarded reports
are not additional worker execution. Expected workers come from xdist's actual
node setup, including `auto`, rather than a guessed worker count.
SELF CPU excludes child-process CPU and cannot by itself identify host contention.

Active coverage core and branch mode are sampled from `Coverage.current()` after
collection and only accepted when that instance is pytest-cov's controller
instance. No new coverage object is created or started. Disabled/unavailable
coverage is `UNKNOWN`; the separate existing pre-test branch probe is never used
as a worker's active core. The controller records the actual checkout's
`git rev-parse HEAD` before test execution, a bounded CPU-model string, and explicit
cache-action outputs: uv/pytest `cache-hit`, artifact-cache `cache-hit` and
`artifact-found`. Unavailable outputs stay null, not guessed misses or hits.
There is no environment dump, hostname, PID, token, cache key or filesystem-path
payload. No additional hosted benchmark or workflow run is introduced.
