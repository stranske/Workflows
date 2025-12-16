# Workflow Templates for Consumer Repos

This directory contains workflow templates that consumer repositories can copy and customize to integrate with this workflow library.

## Quick Start

1. **Copy the workflow you need** to your repo's `.github/workflows/` directory
2. **Customize** the marked sections (module names, paths, etc.)
3. **Set up required secrets** in your repository settings
4. **Commit and push** to enable the workflows

## Available Templates

| Template | Purpose | Complexity |
|----------|---------|------------|
| [ci-basic.yml](ci-basic.yml) | Basic Python CI: lint, type check, test | Simple |
| [ci-full.yml](ci-full.yml) | Full CI: smoke test, lint, coverage, PR gate | Medium |
| [dependency-refresh.yml](dependency-refresh.yml) | Scheduled `requirements.lock` refresh | Simple |
| [cosmetic-repair.yml](cosmetic-repair.yml) | Auto-fix formatting/cosmetic issues | Medium |

## Required Secrets

Most templates use only `GITHUB_TOKEN` (automatically provided). Some advanced features need:

| Secret | Used By | Purpose |
|--------|---------|---------|
| `SERVICE_BOT_PAT` | Agent workflows | Bot account for automated comments |
| `OWNER_PR_PAT` | Agent workflows | PR creation with elevated permissions |
| `BRANCH_PROTECTION_TOKEN` | Health workflows | Override branch protection rules |

## Using Reusable Workflows

Instead of copying templates, you can call workflows directly from this repo:

```yaml
jobs:
  ci:
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main
    with:
      python-version: '3.11'
    secrets: inherit
```

See [docs/ci/WORKFLOWS.md](../docs/ci/WORKFLOWS.md) for the full list of reusable workflows.

## Customization Guide

### Module Names
Replace these placeholders in templates:
- `YOUR_PACKAGE_NAME` → Your Python package name (e.g., `my_project`)
- `YOUR_MODULE_NAME` → Your importable module (e.g., `my_project.core`)

### Test Paths
Update test paths to match your project structure:
- `tests/` → Your test directory
- `tests/test_invariants.py` → Your smoke test file

### Python Version
Most templates default to Python 3.11. Update if needed:
```yaml
python-version: '3.12'
```

## Integration Patterns

### Pattern 1: Minimal (Just CI)
Copy `ci-basic.yml` for simple lint + test on PRs.

### Pattern 2: Standard (CI + Health)
Copy `ci-full.yml` + use reusable health workflows for repo maintenance.

### Pattern 3: Full Automation
Use agent workflows for automated issue-to-PR pipelines:
1. Set up `SERVICE_BOT_PAT` secret
2. Use `agents-63-issue-intake.yml` reusable workflow
3. Configure agent labels on issues
