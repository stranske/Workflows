# Integration Test Setup

This guide describes how to prepare the consumer repository fixture and run the integration tests for the agents dedup workflow behavior.

## Consumer repository fixture

The integration fixture is based on the template at `templates/integration-repo`.

1. Render the fixture into a local directory:
   - `python tools/integration_repo.py .consumer-tests/integration-repo`
2. (Optional) Override the reusable workflow reference:
   - `python tools/integration_repo.py .consumer-tests/integration-repo --workflow-ref owner/repo/.github/workflows/reusable-10-ci-python.yml@branch`
3. (Alternative) Render and run tests in one step:
   - `python scripts/run_consumer_repo_tests.py --force`

## Running integration tests

Run the simulated workflow integration tests in this repository:

- `python -m pytest tests/integration/test_agents_dedup.py -m "not slow"`

Run tests inside the rendered consumer repo fixture:

- `python scripts/run_consumer_repo_tests.py --destination .consumer-tests/integration-repo --pytest-args -m "not slow"`

## Expected output

- Duplicate scenarios should report that similar issues are linked.
- Unique scenarios should pass without duplicate comments.
