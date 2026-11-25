# Using Workflows

This guide explains how to consume the reusable workflows from this repository in your own projects.

## Quick Start

Reference a workflow in your repository:

```yaml
# .github/workflows/ci.yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:

jobs:
  python-ci:
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main
    with:
      python-version: "3.12"
```

## Available Workflows

### Reusable CI Workflows

| Workflow | Description | Usage |
|----------|-------------|-------|
| `reusable-10-ci-python.yml` | Python CI (test, lint, type check) | `uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main` |
| `reusable-12-ci-docker.yml` | Docker build and smoke test | `uses: stranske/Workflows/.github/workflows/reusable-12-ci-docker.yml@main` |
| `reusable-18-autofix.yml` | Automated code formatting | `uses: stranske/Workflows/.github/workflows/reusable-18-autofix.yml@main` |

### Composite Actions

The legacy Autofix composite runs as a step in the caller's working tree.
For standard PR formatting and commit or patch handling, call
[Reusable 18](../.github/workflows/reusable-18-autofix.yml) as a workflow job.

Before calling the composite, check out the consumer repository and copy the
[tool-version file](../.github/workflows/autofix-versions.env) from the same
Workflows revision to `.github/workflows/autofix-versions.env` in the consumer
repository. Use the same path in a Workflows source checkout or ZIP. The consumer
project must support `pip install -e ".[dev]"`.

```yaml
steps:
  - uses: actions/checkout@v7
  - name: Run the legacy Autofix step
    id: autofix
    uses: stranske/Workflows/.github/actions/autofix@main
    with:
      python-version: "3.14"
```

The step exposes `steps.autofix.outputs.changed`, `remaining_issues`, and
`new_issues`. Use `changed` to check whether the fixers modified tracked files.
`remaining_issues` counts Ruff findings after the fixers finish. The step reports
findings without failing. If the checkout provides `scripts/classify_ruff.py`, it
uses that script and the optional `.ruff-residual-allowlist.json` to count new
findings. Otherwise, every remaining finding counts as new. Tool errors and
invalid diagnostic, allowlist, count or per-code data fail the step before it
emits counts.

## Workflow Inputs

### reusable-10-ci-python.yml

These names are guarded against the workflow's real `on.workflow_call.inputs`
by `tests/workflows/test_reusable_workflow_inputs_doc.py`; every input below
must exist in `.github/workflows/reusable-10-ci-python.yml`.

<!-- REUSABLE-10-INPUTS-START -->
| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `python-version` | No | `""` | Explicit single runtime override; omitted selects Python 3.13 and 3.14 |
| `python-versions` | No | `"[]"` | JSON array of Python versions to execute (takes precedence when non-empty) |
| `pytest-workers` | No | `"auto"` | xdist workers; first-party Gate explicitly uses four |
| `working-directory` | No | `"."` | Relative working directory (`.` for repo root) |
| `lint` | No | `true` | Toggle Ruff lint execution |
| `format_check` | No | `true` | Toggle Black format check execution |
| `typecheck` | No | `true` | Toggle mypy execution |
| `coverage` | No | `true` | Toggle coverage instrumentation, packaging, and enforcement |
| `coverage-python-version` | No | `""` | Optional runtime for coverage; when set, must match the primary runtime. Empty instruments every selected runtime |
| `coverage-min` | No | `"70"` | Minimum coverage percentage required to pass |
<!-- REUSABLE-10-INPUTS-END -->

Numeric inputs must be finite; the workflow rejects `NaN`, positive infinity,
and negative infinity before running CI. `coverage-min`, `baseline-coverage`,
and `coverage-alert-drop` accept values from 0 through 100, while
`slow-test-top` and `slow-test-min-seconds` accept non-negative integers.

### reusable-18-autofix.yml

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `auto-commit` | No | `true` | Automatically commit fixes |
| `format-python` | No | `true` | Run black formatting |
| `fix-lint` | No | `true` | Run ruff --fix |

## Secrets

Some workflows require secrets to be passed. The secret names below are guarded
against `reusable-10-ci-python.yml`'s `on.workflow_call.secrets` block by
`tests/workflows/test_reusable_workflow_inputs_doc.py`:

<!-- REUSABLE-10-SECRETS-START -->
```yaml
jobs:
  ci:
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main
    secrets:
      pypi-token: ${{ secrets.PYPI_TOKEN }}  # Optional, for installing private dependencies
```
<!-- REUSABLE-10-SECRETS-END -->

## Versioning

- **`@main` is the single supported pin.** Reference every reusable workflow and
  composite action at `@main`.
- There is **no floating version tag.** A `v1` tag scheme previously existed but
  has been removed; do not pin reusables at the `v1` tag (or any other tag).
- A `@<commit-sha>` pin is supported only for a one-off reproducible build you
  manage yourself — it is not kept current. See
  [INTEGRATION_GUIDE.md → Versioning Strategy](INTEGRATION_GUIDE.md#versioning-strategy)
  for why `@main` is the self-consistent reference.

## Examples

Copy a starter to your repository’s `.github/workflows/` and adapt its marked settings:

- [Basic Python CI](../templates/ci-basic.yml) for formatting, lint and tests, or [Full Python CI](../templates/ci-full.yml) for coverage and a final gate.
- [Node.js CI](../templates/ci-node-basic.yml) for npm projects. For a repository with both languages, give each copied workflow its own filename and set its project paths.
- For Docker, follow the calling job in [Workflows Gate](../.github/workflows/pr-00-gate.yml) and the steps in [Reusable Docker Smoke](../.github/workflows/reusable-12-ci-docker.yml). Your repository needs a Dockerfile and a matching health endpoint.

To set up the managed consumer scaffold, follow the [consumer setup checklist](../templates/consumer-repo/docs/SETUP_CHECKLIST.md). To contribute a new example, follow the [example contribution checklist](CONTRIBUTING.md#workflow-examples).

## Troubleshooting

### Common Issues

1. **Permission denied**: Ensure your workflow has necessary permissions
   ```yaml
   permissions:
     contents: write
     pull-requests: write
   ```

2. **Workflow not found**: Check the workflow path and branch reference

3. **Secret not available**: Pass secrets explicitly using `secrets: inherit` or specific secret names

## Further Reading

- [Workflow System Documentation](ci/WORKFLOW_SYSTEM.md)
- [Reusable CI & Automation Workflows](ci_reuse.md)
- [Integration Guide](INTEGRATION_GUIDE.md)
- [Validation Overview](validation/overview.md)
