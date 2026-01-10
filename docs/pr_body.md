# PR Body Checklist

Use this file as a reference when updating the PR body for integration-test work.

## Consumer repository fixture

- Render the fixture from the integration template:
  - `python tools/integration_repo.py .consumer-tests/integration-repo`
  - Or run `python scripts/run_consumer_repo_tests.py --force` to render and execute tests.
- If you need a custom reusable workflow ref, pass `--workflow-ref owner/repo/.github/workflows/file@ref`.

## Integration test run commands

- Run the dedup integration tests in this repository:
  - `python -m pytest tests/integration/test_agents_dedup.py -m "not slow"`
- Run integration tests inside the rendered consumer repo:
  - `python scripts/run_consumer_repo_tests.py --pytest-args -m "not slow"`

## Notes for the PR body

- Mention the fixture path and workflow ref used.
- Include the exact pytest command and whether it passed.
