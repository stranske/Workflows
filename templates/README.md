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

## Template Synchronization

The templates in this directory are the **source of truth** for configuration patterns. They are automatically synchronized with consumer repos through:

### Sync Architecture

```
Workflows (source of truth)
  ├── health-67 ────────────► validates Integration-Tests
  ├── maint-68 ─────────────► creates PRs in consumer repos
  └── templates/ ───────────► canonical workflow definitions

Integration-Tests
  └── notify-workflows.yml ─► triggers health-67 via repository_dispatch

Consumer Repos (Travel-Plan-Permission, Template)
  └── (receive PRs from maint-68)
```

### Sync Workflows

1. **[health-67-integration-sync-check.yml](../.github/workflows/health-67-integration-sync-check.yml)** - Validates Integration-Tests matches templates
   - Runs on template changes, daily schedule, and `repository_dispatch`
   - Creates issues when drift is detected

2. **[maint-68-sync-consumer-repos.yml](../.github/workflows/maint-68-sync-consumer-repos.yml)** - Pushes updates to consumer repos
   - Runs on releases, template changes, or manual dispatch
   - Creates PRs in registered consumer repos with updated templates
   - Registered repos: Travel-Plan-Permission, Template

3. **[notify-workflows.yml](integration-repo/.github/workflows/notify-workflows.yml)** - Template for Integration-Tests to notify this repo
   - Triggers `repository_dispatch` when config changes
   - Validates against templates in PRs

### Key Sync Rules

- **Templates → Consumer Repos**: When templates change here, maint-68 creates PRs in consumer repos
- **Templates → Integration-Tests**: health-67 validates Integration-Tests matches templates
- **Integration-Tests → Templates**: When Integration-Tests changes, it notifies this repo
- **Daily validation**: Scheduled runs catch any untracked drift

### Consumer Repo File Categories

| Category | Files | Sync Behavior |
|----------|-------|---------------|
| **Thin callers** | `agents-*.yml`, `autofix.yml`, `pr-00-gate.yml` | Full sync from templates |
| **CI config** | `ci.yml` | Repo-specific (not synced) |
| **Version pins** | `autofix-versions.env` | Version updates synced, overrides preserved |
| **Repo-specific** | `maint-*.yml`, custom workflows | Not synced |

### Required: artifact-prefix for Multi-Job Workflows

When a CI workflow has multiple jobs calling `reusable-10-ci-python.yml`, **each job must have a unique `artifact-prefix`** to prevent artifact name conflicts:

```yaml
jobs:
  basic:
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main
    with:
      artifact-prefix: basic-  # Unique prefix!
      # ...

  full:
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main
    with:
      artifact-prefix: full-  # Different prefix!
      # ...
```
