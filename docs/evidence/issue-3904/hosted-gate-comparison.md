# Hosted Gate before/after for issue 3904

Required jobs come from `.github/workflows/pr-00-gate.yml` calling
`.github/workflows/reusable-10-ci-python.yml`. Step times use Actions'
one-second timestamps. Collection, worker execution, and in-pytest reporting
come from the uploaded receipts. JUnit figures are summed worker-seconds,
not wall time.

## Commands

- Runner class: `ubuntu-latest`
- Python versions: 3.13, 3.14
- Coverage Python: `3.14`
- Marker: `not quarantine and not slow`
- Workers input: `4`
- Effective argv: `-m "not quarantine and not slow" --junitxml=pytest-junit.xml [--cov --cov-config=pyproject.toml --cov-report=xml --cov-report=term-missing --cov-report=json on the coverage Python only] -n auto --dist load -n 4 --dist=loadgroup -p ci_test_growth`
- The later -n 4 --dist=loadgroup wins over pytest_args.
- Required Gate no longer schedules Python 3.12. Run 38938420079 used 3.12/3.13 and failed, so it is not this pair.

## Runs and SHAs

- before: [41985113733](https://github.com/stranske/Workflows/actions/runs/41985113733) head `62a8612d29af6aa7b8d778eb14d352de042356bb` tested `51e2aae6d84ef5f25be91cb7cb61ea3c352774ac`
- after: [41992454868](https://github.com/stranske/Workflows/actions/runs/41992454868) head `ccab949a59c9bc03b1a5e7a5cea66bbaee44308c` tested `bcddc346f45cc8bd928b3840252b778b7e1ce2bd`
- Source identity: `True` (pytest invocation `identical`).

## Configuration

- Workflow configuration identical: `True`.
- Timing controlled (no CPU or cache confounder): `True`.
- No workflow, worker, coverage, CPU, or cache differences recorded.

## Counts

- Python 3.13 full collection: 50680 -> 45538
- Python 3.13 scoped three files: 37177 -> 32028
- Python 3.14 full collection: 50680 -> 45538
- Python 3.14 scoped three files: 37177 -> 32028

## Branch coverage

- Python 3.14 `scripts/langchain/pr_verifier.py` lost lines 0, lost branches 0, gained lines 0, gained branches 0.
- Aggregate percent 92.49 -> 92.48 is not the equivalence result.
- Executed verifier lines 3030 -> 3030; branches 1168 -> 1168.

## Timings

- Python 3.13 before: job wall 674.000s, startup 20.000s, pytest step 646.000s, collection 46.865s, max worker 631.972s, controller 638.992s, in-pytest reporting null, record-summary 0.000s, scoped JUnit worker-seconds 801.976s.
- Python 3.13 after: job wall 604.000s, startup 25.000s, pytest step 567.000s, collection 46.669s, max worker 555.094s, controller 561.448s, in-pytest reporting null, record-summary 0.000s, scoped JUnit worker-seconds 529.264s.
- Python 3.14 before: job wall 463.000s, startup 20.000s, pytest step 431.000s, collection 28.950s, max worker 394.968s, controller 423.757s, in-pytest reporting null, record-summary 0.000s, scoped JUnit worker-seconds 461.931s.
- Python 3.14 after: job wall 412.000s, startup 22.000s, pytest step 377.000s, collection 29.699s, max worker 343.198s, controller 370.140s, in-pytest reporting null, record-summary 0.000s, scoped JUnit worker-seconds 299.053s.
- xdist collection overlaps worker execution, so collection and worker clocks are not added together. A null in-pytest reporting value means the controller clock does not leave a nonnegative remainder after both.

## Ten-minute target and residual cost

- Slowest after python-job wall: 604.000s.
- Target met (<600s job wall): `False`.
- Residual gap: 4.000s above the job-wall target. This does not claim the target is met.

Dominant JUnit suites after the change:

- Python 3.13: `tests.scripts.test_pr_verifier_delivery_destinations` 407.623s worker-seconds
- Python 3.13: `tests.scripts.test_check_deliberate_break` 144.976s worker-seconds
- Python 3.13: `tests.scripts.test_pr_verifier_prompt_coverage` 96.651s worker-seconds
- Python 3.14: `tests.scripts.test_pr_verifier_delivery_destinations` 228.104s worker-seconds
- Python 3.14: `tests.scripts.test_check_deliberate_break` 93.975s worker-seconds
- Python 3.14: `tests.scripts.test_pr_verifier_prompt_coverage` 55.364s worker-seconds

Dominant JUnit functions after the change:

- Python 3.13: `tests.workflows.test_agents_guard_publication::test_actual_head_publisher` 47.360s worker-seconds
- Python 3.13: `tests.scripts.test_check_deliberate_break::test_base_pytest_must_execute_a_test_before_counting_as_red` 36.870s worker-seconds
- Python 3.13: `tests.scripts.test_pr_verifier_delivery_destinations::test_product_chain_inherits_latest_explicit_governor_and_aspect` 34.081s worker-seconds
- Python 3.13: `tests.workflows.test_verifier_expanded_comparison::test_expanded_each_arm_blocks_pass` 29.455s worker-seconds
- Python 3.13: `tests.scripts.test_pr_verifier_delivery_destinations::test_component_relative_presence_preserves_parent_actual_floor` 29.096s worker-seconds
- Python 3.14: `tests.workflows.test_agents_guard_publication::test_actual_head_publisher` 26.516s worker-seconds
- Python 3.14: `tests.scripts.test_check_deliberate_break::test_base_pytest_must_execute_a_test_before_counting_as_red` 23.586s worker-seconds
- Python 3.14: `tests.scripts.test_pr_verifier_delivery_destinations::test_product_chain_inherits_latest_explicit_governor_and_aspect` 18.302s worker-seconds
- Python 3.14: `tests.workflows.test_verifier_expanded_comparison::test_expanded_each_arm_blocks_pass` 17.819s worker-seconds
- Python 3.14: `tests.scripts.test_pr_verifier_delivery_destinations::test_component_relative_presence_preserves_parent_actual_floor` 16.809s worker-seconds
