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

| Named regression | Old cases | Retained classifier cases |
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
A local run does not establish hosted performance. Do not close #3904 or claim a
sub-10-minute Gate until controlled hosted evidence supports that claim. If the
runtime target remains unmet, name the measured residual bottlenecks and gap.
