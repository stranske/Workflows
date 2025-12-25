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
      python-version: "3.11"
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
  - uses: stranske/Workflows/.github/actions/autofix@main
    with:
      token: ${{ secrets.GITHUB_TOKEN }}
      
  - uses: stranske/Workflows/.github/actions/python-setup@main
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
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main
    secrets:
      CODECOV_TOKEN: ${{ secrets.CODECOV_TOKEN }}
```

## Versioning

- Use `@main` for latest stable version
- Use `@v1.0.0` (when released) for specific versions
- Use `@<commit-sha>` for specific commits

## Examples

See the [examples directory](docs/examples/) for complete working configurations:

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

- [Workflow System Documentation](docs/ci/WORKFLOWS.md)
- [Autofix Logic](docs/ci/AUTOFIX.md)
- [Configuration Reference](CONFIGURATION.md)
