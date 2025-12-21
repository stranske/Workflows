# Integration Guide: Using Workflows in Your Repository

This guide explains how to integrate the stranske/Workflows workflow library into your Python project.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Integration Methods](#integration-methods)
3. [Reusable Workflows](#reusable-workflows)
4. [Template Workflows](#template-workflows)
5. [Required Setup](#required-setup)
6. [Common Patterns](#common-patterns)
7. [Troubleshooting](#troubleshooting)

---

## Quick Start

### Minimal Setup (5 minutes)

1. **Create `.github/workflows/ci.yml`** in your repo:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  ci:
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@v1
    with:
      python-version: '3.11'
```

2. **Commit and push** - CI will run on your next PR!

---

## Versioning Strategy

Choose the reference that matches your stability needs:

| Reference | When to use it | Behavior |
|-----------|----------------|----------|
| **Floating major tag (`@v1`)** | Default for most teams that want security/bug fixes without breaking changes. | Automatically moves forward to the latest `v1.x` release; maintained by the release workflow and the floating-tag maintenance job. |
| **Pinned release (`@v1.0.0`)** | When you need fully reproducible builds or plan to upgrade on your own schedule. | Locked to a specific release until you update the tag. |
| **Branch reference (`@main`)** | Only when testing unreleased changes. | Can include breaking changes; not guaranteed stable. |

Example with both floating and pinned tags:

```yaml
jobs:
  ci-floating:
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@v1
    with:
      python-version: '3.11'

  ci-pinned:
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@v1.0.0
    with:
      python-version: '3.11'
```

---

## Integration Methods

### Method 1: Reusable Workflows (Recommended)

Call workflows directly from this library. Changes propagate automatically.

```yaml
jobs:
  python-ci:
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@v1
    with:
      python-version: '3.11'
    secrets: inherit
```

**Pros:**
- Always up-to-date
- No maintenance needed
- Consistent across repos

**Cons:**
- Less customizable
- Depends on external repo

### Method 2: Template Workflows

Copy templates from `/templates/` and customize for your project.

```bash
# Copy template to your repo
curl -sL https://raw.githubusercontent.com/stranske/Workflows/main/templates/ci-basic.yml \
  -o .github/workflows/ci.yml
```

**Pros:**
- Full control
- No external dependencies
- Easy customization

**Cons:**
- Manual updates needed
- Can drift from best practices

### Method 3: Hybrid Approach

Use reusable workflows for standard CI, templates for custom needs.

```yaml
jobs:
  # Standard CI via reusable workflow
  ci:
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@v1

  # Custom job specific to your project
  integration-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: ./run-integration-tests.sh
```

---

## Reusable Workflows

### CI Workflows

| Workflow | Purpose | Inputs |
|----------|---------|--------|
| `reusable-10-ci-python.yml` | Full Python CI pipeline | `python-version`, `coverage-threshold` |
| `reusable-99-selftest.yml` | Run self-tests on workflow files | - |

## Workflow Outputs

Caller-facing outputs are available only from a subset of reusable workflows. If a workflow is not listed below it exports no `workflow_call` outputs (it still produces artifacts and step summaries).

| Workflow | Outputs (name → description) |
|----------|-----------------------------|
| `reusable-16-agents.yml` | `readiness_report` → JSON payload from the readiness probe; `readiness_table` → Markdown table summarizing assignable agents. |
| `reusable-70-orchestrator-init.yml` | `rate_limit_safe`, `has_work`, `token_source`; keepalive/run toggles (`enable_keepalive`, `keepalive_pause_label`, `keepalive_round`, `keepalive_pr`, `keepalive_max_retries`, `keepalive_trace`); readiness/diagnostic toggles (`enable_readiness`, `readiness_agents`, `readiness_custom_logins`, `require_all`, `enable_preflight`, `enable_diagnostic`, `diagnostic_attempt_branch`, `diagnostic_dry_run`, `enable_verify_issue`, `verify_issue_number`, `verify_issue_valid_assignees`); bootstrap/worker settings (`enable_bootstrap`, `bootstrap_issues_label`, `draft_pr`, `dispatcher_force_issue`, `worker_max_parallel`, `conveyor_max_merges`); misc orchestrator options (`codex_user`, `codex_command_phrase`, `enable_watchdog`, `dry_run`, `options_json`). |
| `reusable-10-ci-python.yml` | None (artifacts only: coverage, metrics, summaries). |
| `reusable-11-ci-node.yml` | None (artifacts only: coverage + junit when enabled). |
| `reusable-12-ci-docker.yml` | None (logs only). |
| `reusable-18-autofix.yml` | None (patch artifacts + summaries). |
| `reusable-70-orchestrator-main.yml` | None (consumes init outputs; exports status via summaries). |
| `reusable-agents-issue-bridge.yml` | None (bridge PR creation artifacts/logs). |

### Using outputs in dependent jobs

Orchestrator chaining example:

```yaml
jobs:
  orchestrator-init:
    uses: stranske/Workflows/.github/workflows/reusable-70-orchestrator-init.yml@v1
    id: init

  orchestrator-main:
    needs: orchestrator-init
    if: needs.init.outputs.has_work == 'true' && needs.init.outputs.rate_limit_safe == 'true'
    uses: stranske/Workflows/.github/workflows/reusable-70-orchestrator-main.yml@v1
    with:
      init_success: ${{ needs.init.result }}
      enable_keepalive: ${{ needs.init.outputs.enable_keepalive }}
      keepalive_pause_label: ${{ needs.init.outputs.keepalive_pause_label }}
      keepalive_round: ${{ needs.init.outputs.keepalive_round }}
      keepalive_pr: ${{ needs.init.outputs.keepalive_pr }}
      options_json: ${{ needs.init.outputs.options_json }}
      token_source: ${{ needs.init.outputs.token_source }}
```

Agent readiness example (posting the Markdown table):

```yaml
jobs:
  agents-readiness:
    uses: stranske/Workflows/.github/workflows/reusable-16-agents.yml@v1
    id: readiness
    with:
      enable_readiness: 'true'

  comment-readiness:
    needs: readiness
    if: needs.readiness.outputs.readiness_table != ''
    runs-on: ubuntu-latest
    steps:
      - name: Post readiness table
        uses: actions/github-script@v7
        with:
          script: |
            const table = `## Agent Readiness\n\n${{ toJSON(needs.readiness.outputs.readiness_table) }}`;
            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body: table,
            });
```


### Agent Workflows

| Workflow | Purpose | Required Secrets |
|----------|---------|------------------|
| `reusable-agents-issue-bridge.yml` | Convert issues to PRs via agents | `service_bot_pat`, `owner_pr_pat` |

### Example: Full CI

```yaml
name: CI

on: [push, pull_request]

jobs:
  ci:
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@v1
    with:
      python-version: '3.11'
      run-tests: true
      check-types: true
      coverage-threshold: 80
    secrets:
      pypi: ${{ secrets.PYPI_TOKEN }}  # Optional, for publishing
```

---

## Template Workflows

Copy from `/templates/` and customize:

| Template | Use Case |
|----------|----------|
| `ci-basic.yml` | Simple projects: lint + test |
| `ci-full.yml` | Production projects: full pipeline with gate |
| `dependency-refresh.yml` | Keep `requirements.lock` updated |
| `cosmetic-repair.yml` | Auto-fix formatting issues |

### Customization Checklist

After copying a template:

- [ ] Replace `YOUR_PACKAGE_NAME` with your package
- [ ] Update test paths (`tests/`)
- [ ] Update source paths (`src/`)
- [ ] Set Python version(s)
- [ ] Configure coverage threshold
- [ ] Add required secrets

---

## Required Setup

### Repository Secrets

Set these in your repo's Settings → Secrets → Actions:

| Secret | When Needed | How to Create |
|--------|-------------|---------------|
| `GITHUB_TOKEN` | Always | Automatic |
| `SERVICE_BOT_PAT` | Agent workflows | Create PAT with `repo` scope |
| `OWNER_PR_PAT` | Agent PR creation | Create PAT with `repo` scope |
| `PYPI_TOKEN` | Publishing packages | From pypi.org |

### Branch Protection

For the gate pattern to work:

1. Go to Settings → Branches → Add rule
2. Set branch pattern: `main`
3. Enable "Require status checks"
4. Add required checks: `CI Gate`, `Lint`, `Test`

---

## Common Patterns

### Pattern 1: PR Gate

Use a gate job that branch protection requires:

```yaml
jobs:
  lint:
    # ...
  test:
    # ...
  
  gate:
    name: CI Gate
    needs: [lint, test]
    if: always()
    runs-on: ubuntu-latest
    steps:
      - name: Check results
        run: |
          if [[ "${{ needs.lint.result }}" != "success" ]] || \
             [[ "${{ needs.test.result }}" != "success" ]]; then
            exit 1
          fi
```

### Pattern 2: Matrix Testing

Test across Python versions:

```yaml
jobs:
  test:
    strategy:
      matrix:
        python-version: ['3.10', '3.11', '3.12']
    steps:
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
```

### Pattern 3: Conditional Jobs

Skip expensive jobs for draft PRs:

```yaml
jobs:
  full-test:
    if: github.event.pull_request.draft == false
    # ...
```

---

## Troubleshooting

### "Workflow file issue" Error

**Cause:** YAML syntax error or invalid workflow structure.

**Fix:** Validate your workflow:
```bash
# Install actionlint
brew install actionlint

# Check workflow
actionlint .github/workflows/your-workflow.yml
```

### "Resource not accessible" Error

**Cause:** Missing permissions or secrets.

**Fix:** Add permissions block:
```yaml
permissions:
  contents: read
  pull-requests: write
```

### Reusable Workflow Not Found

**Cause:** Wrong path or ref.

**Fix:** Use full path with `@ref`:
```yaml
uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main
```

### Jobs Not Running

**Cause:** `if` condition evaluating to false.

**Fix:** Check concurrency groups and conditions. For `workflow_dispatch`, ensure fallbacks:
```yaml
concurrency:
  group: ci-${{ github.event.pull_request.number || github.run_id }}
```

---

## Getting Help

- **Documentation:** See `docs/ci/WORKFLOWS.md` for detailed workflow descriptions
- **Issues:** Open an issue in stranske/Workflows for bugs or feature requests
- **Templates:** Check `/templates/` for copy-paste solutions
