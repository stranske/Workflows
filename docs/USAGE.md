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
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@v1
    with:
      python-version: "3.11"
```

## Available Workflows

### Reusable CI Workflows

| Workflow | Description | Usage |
|----------|-------------|-------|
| `reusable-10-ci-python.yml` | Python CI (test, lint, type check) | `uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@v1` |
| `reusable-12-ci-docker.yml` | Docker build and smoke test | `uses: stranske/Workflows/.github/workflows/reusable-12-ci-docker.yml@v1` |
| `reusable-18-autofix.yml` | Automated code formatting | `uses: stranske/Workflows/.github/workflows/reusable-18-autofix.yml@v1` |
| `reusable-16-agents.yml` | Agent orchestration | `uses: stranske/Workflows/.github/workflows/reusable-16-agents.yml@v1` |

### Composite Actions

Use actions directly in your workflow steps:

```yaml
steps:
  - uses: stranske/Workflows/.github/actions/autofix@v1
    with:
      token: ${{ secrets.GITHUB_TOKEN }}
      
  - uses: stranske/Workflows/.github/actions/python-ci-setup@v1
    with:
      python-version: "3.11"
```

## Workflow Inputs

### reusable-10-ci-python.yml

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `python-version` | No | `"3.11"` | Python version to use |
| `run-tests` | No | `true` | Run pytest |
| `run-lint` | No | `true` | Run ruff linting |
| `run-typecheck` | No | `true` | Run mypy type checking |

### reusable-18-autofix.yml

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `auto-commit` | No | `true` | Automatically commit fixes |
| `format-python` | No | `true` | Run black formatting |
| `fix-lint` | No | `true` | Run ruff --fix |

## Secrets

Some workflows require secrets to be passed:

```yaml
jobs:
  ci:
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@v1
    secrets:
      CODECOV_TOKEN: ${{ secrets.CODECOV_TOKEN }}
```

## Versioning

- Use `@v1` for the current stable major line
- Use `@v1.0.0` (or newer) for fully pinned releases
- Use `@<commit-sha>` for specific commits
- Use `@main` only when you intentionally need unreleased changes

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
