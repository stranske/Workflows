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
| `reusable-16-agents.yml` | Agent orchestration | `uses: stranske/Workflows/.github/workflows/reusable-16-agents.yml@main` |

### Composite Actions

Use actions directly in your workflow steps:

```yaml
steps:
  - uses: stranske/Workflows/.github/actions/autofix@v1
    with:
      token: ${{ secrets.GITHUB_TOKEN }}
      
  - uses: stranske/Workflows/.github/actions/python-ci-setup@v1
    with:
      python-version: "3.12"
```

## Workflow Inputs

### reusable-10-ci-python.yml

These names are guarded against the workflow's real `on.workflow_call.inputs`
by `tests/workflows/test_reusable_workflow_inputs_doc.py`; every input below
must exist in `.github/workflows/reusable-10-ci-python.yml`.

<!-- REUSABLE-10-INPUTS-START -->
| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `python-version` | No | `"3.12"` | Primary Python version when `python-versions` is not provided |
| `python-versions` | No | `"[]"` | JSON array of Python versions to execute (takes precedence when non-empty) |
| `working-directory` | No | `"."` | Relative working directory (`.` for repo root) |
| `lint` | No | `true` | Toggle Ruff lint execution |
| `format_check` | No | `true` | Toggle Black format check execution |
| `typecheck` | No | `true` | Toggle mypy execution |
| `coverage` | No | `true` | Toggle coverage instrumentation, packaging, and enforcement |
| `coverage-min` | No | `"70"` | Minimum coverage percentage required to pass |
<!-- REUSABLE-10-INPUTS-END -->

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

- Use `@main` for the current first-party consumer default
- Use `@<commit-sha>` for reproducible pinned integrations
- Use alternate refs only when you intentionally need a separate distribution or test surface

## Examples

See the [examples directory](examples/) for complete working configurations:

- Python project CI
- Multi-language projects
- Docker-based projects

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
