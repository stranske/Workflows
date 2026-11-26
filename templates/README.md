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
| [ci-node-basic.yml](ci-node-basic.yml) | Shared CI for Node.js and TypeScript projects using npm and Jest by default | Simple |
| [cosmetic-repair.yml](cosmetic-repair.yml) | Auto-fix formatting/cosmetic issues | Medium |

### Node.js CI starter

Commit `package.json` and the lockfile for your package manager in the
configured working directory. The starter defaults to npm and requires
`package-lock.json`. The pnpm and Yarn installs require `pnpm-lock.yaml` and
`yarn.lock`, respectively.

For each enabled check, provide the corresponding `package.json` script
(`lint`, `format:check`, `typecheck` or `test`) or install its fallback tool as
a project dependency (ESLint, Prettier, TypeScript, or Jest/Vitest). Tests
default to Jest with coverage. Use the
[Node CI inputs](../docs/INTEGRATION_GUIDE.md#ci-workflows) to select Vitest or
disable checks your project does not use.

### Standalone maintenance copies

Copy the cosmetic repair workflow from a Workflows checkout. Run the commands
from your project root and set `workflows` to the checkout path.

```bash
workflows=/path/to/Workflows
mkdir -p .github/workflows
cp "$workflows/templates/cosmetic-repair.yml" .github/workflows/
```

Your repository owns the copy. Customize paths and inputs there, and review
upstream changes when you want to update it.

### Dependency lock preview

Registered consumers use the [fleet Renovate preset](../renovate-presets/fleet.json)
for routine dependency proposals and weekly `requirements.lock` maintenance.
Workflows-Integration-Tests also regenerates its own lock through
[Maint 69](../.github/workflows/maint-69-sync-integration-repo.yml) when synchronizing
integration sources and tool pins.

For a local preview, run the command recorded in your project's lockfile in a
disposable checkout. Keep its input files, Python target, extras, and output
options. Add `--upgrade`, then review `git diff -- requirements.lock`. The actual
integration project uses this command and selects its `test` and `dev` extras.

```bash
uv pip compile --python-version 3.13 --upgrade pyproject.toml \
  --extra test --extra dev --universal --output-file requirements.lock
git diff -- requirements.lock
```

When the preview matches the intended update, regenerate the lock on your
project branch and open it through your normal dependency PR process.

For an existing or custom repository-owned workflow, the
[archived standalone recipe](https://github.com/stranske/Workflows/blob/3c2524c625d0bd46c3208abc2f6ec44050363674/templates/dependency-refresh.yml)
preserves the original manual dry run and twice-monthly schedule. Its SHA-256
is `dd1d6835a27a3cad0867003a0926165ee4e530ed97fc43b999fdbc238e5a546a`.
Verify it from a Workflows checkout.

```bash
git show 3c2524c625d0bd46c3208abc2f6ec44050363674:templates/dependency-refresh.yml |
  shasum -a 256
```

### Python CI starter for the GitHub Actions gallery

To run the shared Python CI workflow in one project, copy
[python-ci.yml](workflow-templates/python-ci.yml) to the project’s
`.github/workflows/` directory. The starter targets `main` on pushes and pull
requests. Set both branch filters to the project's default branch if it differs.

To publish the starter in an organization's **Actions → New workflow** gallery,
copy the three files in [workflow-templates](workflow-templates/) into the
root `workflow-templates/` directory of the organization's `.github` repository.
Keep `python-ci.yml`, `python-ci.properties.json` and `python.svg` together.
For organizations with different default branches, use GitHub’s `$default-branch`
placeholder in both branch filters in the published copy.
The shared CI installs project dependencies from `requirements.lock` or an
installable Python project. A project with only `requirements.txt` must provide
one of those before using this starter. The starter runs with public dependencies
and requests no caller secrets.

[GitHub's workflow template guide](https://docs.github.com/en/actions/how-tos/reuse-automations/create-workflow-templates)

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
      python-version: '3.14'
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
Templates use Python 3.14 as the primary runtime and run standard CI matrices on
Python 3.13/3.14 (3.12 is retired). Adjust only if your repo has a real runtime requirement:
```yaml
python-version: '3.14'
python-versions: '["3.13", "3.14"]'
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

The [consumer sync manifest](../.github/sync-manifest.yml) defines which files Maint 68 distributes to registered repositories. Standalone maintenance copies stay under the receiving repository’s ownership.

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

- **Managed files → Consumer Repos**: Maint 68 creates PRs for files selected by the compiled consumer sync manifest.
- **Templates → Integration-Tests**: health-67 validates Integration-Tests matches templates
- **Integration-Tests → Templates**: When Integration-Tests changes, it notifies this repo
- **Daily validation**: Scheduled runs catch any untracked drift

### Consumer Repo File Categories

| Category | Files | Sync Behavior |
|----------|-------|---------------|
| **Thin callers** | `agents-*.yml`, `autofix.yml`, `pr-00-gate.yml` | Full sync from templates |
| **CI config** | `ci.yml` | Repo-specific (not synced) |
| **Version pins** | `autofix-versions.env` | Synced by maint-52 with matching `pyproject.toml`/`requirements.lock` changes |
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
