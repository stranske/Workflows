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


### Workflow Permissions

**Critical for reusable workflows:** The repository must have write permissions enabled.

1. Go to Settings → Actions → General
2. Scroll to "Workflow permissions"
3. Select **"Read and write permissions"**
4. Check **"Allow GitHub Actions to create and approve pull requests"**
5. Click Save

Without these settings, workflows calling reusable workflows from this repo will fail
with `startup_failure` status and no useful error message.

**Via API (for automation):**
```bash
gh api repos/OWNER/REPO/actions/permissions/workflow -X PUT --input - << 'EOF'
{"default_workflow_permissions": "write", "can_approve_pull_request_reviews": true}
EOF
```

### Consumer Repo Setup: Required Scripts

The reusable `reusable-10-ci-python.yml` workflow runs two scripts from the
consumer repository. Add these files to your repo or CI will fail:

- `scripts/sync_test_dependencies.py` (validates test imports vs. dev deps)
- `tools/resolve_mypy_pin.py` (selects the Python version used by mypy)

You can copy the reference implementations from:

- `templates/integration-repo/scripts/sync_test_dependencies.py`
- `templates/integration-repo/tools/resolve_mypy_pin.py`

### Consumer Repo Setup: .gitignore Entries

**Critical for keepalive/codex workflows:** Add these entries to your `.gitignore`
to prevent merge conflicts when multiple PRs run concurrently:

```gitignore
# Codex working files (preserved via workflow artifacts, not git)
# CRITICAL: These must be gitignored to prevent merge conflicts when
# multiple PRs run keepalive simultaneously. Each run rebuilds these files.
# Generic names (legacy)
codex-prompt.md
codex-output.md
# PR-specific names (used by reusable-codex-run.yml to avoid conflicts)
codex-prompt-*.md
codex-output-*.md
verifier-context.md
```

**Why this matters:** When multiple PRs run keepalive concurrently, each workflow
generates these working files. The workflow uses PR-specific filenames (e.g.,
`codex-output-123.md`) and explicitly excludes them from commits, but the
`.gitignore` provides defense-in-depth. Historical data is preserved in:
- PR comments (completion summaries)
- Workflow artifacts (full outputs)
- Commit messages (change descriptions)

### Consumer Repo Setup: Coverage Soft Gate

Enable coverage tracking with automatic issue creation when coverage drops:

**1. Enable soft-gate in your Gate workflow:**

```yaml
jobs:
  python-ci:
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main
    with:
      coverage-min: "80"           # Minimum threshold
      enable-soft-gate: true       # Enable trend tracking & hotspot reporting
      artifact-prefix: "gate-"     # Required for coverage guard
```

**2. Create a coverage baseline file (`config/coverage-baseline.json`):**

```json
{
  "coverage": 80.0,
  "updated": "2025-12-30",
  "notes": "Initial baseline - adjust based on project maturity"
}
```

**3. Add the coverage guard workflow (`.github/workflows/maint-coverage-guard.yml`):**

Copy from `templates/consumer-repo/.github/workflows/maint-coverage-guard.yml`

**What you get:**

| Feature | Description |
|---------|-------------|
| **Coverage Summary** | Table in workflow run summary showing current vs baseline |
| **Hotspot Report** | List of files with lowest coverage (candidates for new tests) |
| **Low Coverage Alert** | Files below 50% threshold highlighted separately |
| **Baseline Issue** | Auto-created/updated issue when coverage drops below baseline |
| **Trend Artifacts** | `coverage-trend.json` and `coverage-trend-history.ndjson` for analysis |

**Soft vs Hard Gate:**

- **Soft gate** (`enable-soft-gate: true`): Reports coverage but doesn't fail the build
- **Hard gate** (`coverage-min: "80"`): Fails build if coverage below threshold

Use both together for maximum visibility: soft gate shows trends while hard gate
enforces the minimum.

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


### Startup Failure (No Error Message)

**Cause:** Repository workflow permissions set to "Read" instead of "Read and write".

**Symptoms:**
- Workflow shows `startup_failure` status
- No error message or logs available
- Same workflow works in other repositories
- Only affects workflows calling reusable workflows

**Fix:** Update repository workflow permissions:
1. Go to Settings → Actions → General
2. Set "Workflow permissions" to **"Read and write permissions"**
3. Enable **"Allow GitHub Actions to create and approve pull requests"**


### Startup Failure (Caller Workflow Permissions)

**Cause:** Caller workflow has a top-level `permissions:` block when calling a reusable workflow.

**Symptoms:**
- Same as above: `startup_failure`, no logs, zero jobs started
- The reusable workflow also specifies permissions

**Fix:** Remove the `permissions:` block from the caller workflow:
```yaml
# WRONG - causes startup_failure
permissions:
  contents: read
  pull-requests: write

jobs:
  ci:
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main

# CORRECT - let the reusable workflow handle permissions
jobs:
  ci:
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main
```

---

## Consumer Repo Setup (Full Automation)

For repositories that want full CI + agent automation (Codex keepalive, autofix, etc.):

### Quick Setup

Copy all workflow templates from `/templates/consumer-repo/.github/workflows/` to your repository:

```bash
# Clone templates
mkdir -p .github/workflows
curl -sL https://raw.githubusercontent.com/stranske/Workflows/main/templates/consumer-repo/.github/workflows/ci.yml -o .github/workflows/ci.yml
curl -sL https://raw.githubusercontent.com/stranske/Workflows/main/templates/consumer-repo/.github/workflows/autofix-versions.env -o .github/workflows/autofix-versions.env
curl -sL https://raw.githubusercontent.com/stranske/Workflows/main/templates/consumer-repo/.github/workflows/agents-issue-intake.yml -o .github/workflows/agents-issue-intake.yml
curl -sL https://raw.githubusercontent.com/stranske/Workflows/main/templates/consumer-repo/.github/workflows/agents-orchestrator.yml -o .github/workflows/agents-orchestrator.yml
curl -sL https://raw.githubusercontent.com/stranske/Workflows/main/templates/consumer-repo/.github/workflows/agents-pr-meta.yml -o .github/workflows/agents-pr-meta.yml
curl -sL https://raw.githubusercontent.com/stranske/Workflows/main/templates/consumer-repo/.github/workflows/autofix.yml -o .github/workflows/autofix.yml
```

### Workflow Summary

| Workflow | Purpose | Triggers |
|----------|---------|----------|
| `ci.yml` | Python CI (lint, format, tests, typecheck) | push, PR |
| `agents-issue-intake.yml` | Assigns Codex/Copilot to issues | issue labeled `agent:codex` |
| `agents-orchestrator.yml` | Scheduled keepalive sweeps | every 30 min |
| `agents-pr-meta.yml` | Detects keepalive comments, dispatches continuation | PR comments |
| `autofix.yml` | Auto-fixes lint/format issues | PR sync, `autofix` label |
| `autofix-versions.env` | Pins tool versions | N/A |

### Required Secrets

| Secret | Purpose | Required For |
|--------|---------|--------------|
| `SERVICE_BOT_PAT` | Bot account for comments/labels (stranske-automation-bot) | agents, autofix |
| `ACTIONS_BOT_PAT` | Workflow dispatch triggers | orchestrator, pr-meta |
| `OWNER_PR_PAT` | Create PRs on behalf of user | issue-intake |

### Dual Checkout Architecture

Consumer repo workflows use the **dual checkout pattern**:

1. **Consumer repo** is checked out for your code
2. **Workflows repo** is checked out (sparse) for scripts

This means:
- ✅ Consumer repos still provide CI helper scripts in `scripts/` and `tools/`
- ✅ Automation scripts under `.github/scripts/` stay **up-to-date** from Workflows
- ✅ **No sync required** when Workflows scripts change
- ✅ Only **thin caller workflows** (~50-100 lines each) in your repo

### What Each Workflow Does

#### `agents-pr-meta.yml` (Critical for Keepalive)

This is the **key workflow** for Codex keepalive. When Codex completes a round of work, it posts a comment with a keepalive marker. This workflow:

1. Detects the keepalive marker in PR comments
2. Validates the comment is from an authorized user
3. Dispatches the orchestrator to continue work
4. Updates PR body with status sections

Without this workflow, Codex PRs will stall after the first round.

#### `autofix.yml`

When a PR has lint/format issues:

1. Autofix runs Black and Ruff with `--fix`
2. Commits fixes directly to the PR branch
3. Labels PR with `autofix:applied`
4. Posts a summary comment

This eliminates manual formatting work and ensures consistent style.

##### Dynamic Target Detection

Autofix automatically detects Python directories by finding all `.py` files in the repository. Standard non-source directories are excluded by default:

- `.git`, `.venv`, `venv`, `.env`, `env`
- `__pycache__`, `node_modules`
- `build`, `dist`, `.eggs`, `*.egg-info`
- `.tox`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`
- `htmlcov`, `.coverage`

##### Custom Exclusions (`.autofix-exclude`)

To exclude additional directories from autofix (e.g., generated code, vendor packages, legacy modules), create a `.autofix-exclude` file in your repository root:

```
# .autofix-exclude
# Comments start with #

# Exclude generated migrations
migrations/

# Exclude vendored code
vendor/
third_party/

# Exclude legacy modules being deprecated
legacy_api/
```

Each line specifies a directory to exclude. This file is optional - if not present, only standard exclusions apply.

---

## Getting Help

- **Documentation:** See `docs/ci/WORKFLOWS.md` for detailed workflow descriptions
- **Issues:** Open an issue in stranske/Workflows for bugs or feature requests
- **Templates:** Check `/templates/` for copy-paste solutions
- **Consumer templates:** See `/templates/consumer-repo/` for full automation setup

---

## CI Failure Routing

The keepalive system intelligently routes CI failures to the appropriate fix mechanism:

### Decision Flow

```
┌──────────────────────────────────────────────────────────────────┐
│                     Gate Workflow Result                         │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  Gate Passed?   │
                    └─────────────────┘
                              │
              ┌───────────────┴───────────────┐
              │ Yes                           │ No
              ▼                               ▼
    ┌─────────────────┐  ┌─────────────────┐
    │  Normal Work    │  │ Classify Failure│
    │  (run action)   │  └─────────────────┘
    │                 │           │
    │  Prompt:        │     ┌─────┴─────┐
    │  keepalive_     │     │           │
    │  next_task.md   │     ▼           ▼
    └─────────────────┘  ┌───────┐  ┌──────────────┐
                         │ Lint/ │  │ Tests/Mypy/  │
                         │Format │  │ Unknown      │
                         └───┬───┘  └──────┬───────┘
                             │             │
                             ▼             ▼
                     ┌────────────┐  ┌─────────────────┐
                     │  Autofix   │  │   Fix Mode      │
                     │  Workflow  │  │  (fix action)   │
                     │            │  │                 │
                     │  Black +   │  │  Prompt:        │
                     │  Ruff      │  │  fix_ci_        │
                     └────────────┘  │  failures.md    │
                                     └─────────────────┘
```

### How It Works

1. **Gate Evaluation**: When the keepalive loop evaluates, it checks the gate workflow status

2. **Failure Classification**: If the gate failed, the system inspects which jobs failed:
   - **Test failures**: Jobs with names containing `test`, `pytest`, `unittest`
   - **Mypy failures**: Jobs with names containing `mypy`, `type`, `typecheck`
   - **Lint failures**: Jobs with names containing `lint`, `ruff`, `black`, `format`

3. **Routing Decision**:
   - **Lint/Format failures** → Route to **Autofix** (Black + Ruff can fix these automatically)
   - **Test/Mypy failures** → Route to **Codex with fix_ci_failures.md prompt** (requires code changes)
   - **Unknown failures** → Route to **Codex with fix_ci_failures.md prompt** (needs investigation)

### Prompt Files

| Prompt | Purpose | When Used |
|--------|---------|-----------|
| `keepalive_next_task.md` | Normal task work | Gate passed, tasks remaining |
| `fix_ci_failures.md` | Focus on fixing CI | Test/mypy failures detected |

### Output Variables

The `evaluate` job outputs these new fields:

| Output | Description | Values |
|--------|-------------|--------|
| `prompt_mode` | Which prompt mode to use | `normal`, `fix_ci` |
| `prompt_file` | Full path to prompt file | Path to `.md` file |
| `reason` | Why this action was chosen | `fix-test`, `fix-mypy`, `fix-unknown`, etc. |

### Action Types

| Action | Description | Triggers |
|--------|-------------|----------|
| `run` | Normal Codex run | Gate passed, tasks remaining |
| `fix` | CI fix mode | Test/mypy failure detected |
| `wait` | Wait for gate | Gate pending or lint failure (autofix handles) |
| `stop` | Stop iteration | Tasks complete or max iterations |
| `skip` | Skip entirely | Keepalive disabled |

### Example Scenarios

**Scenario 1: Tests Failing**
```
Gate Status: failure
Failed Jobs: [test (3.11), test (3.12)]
Classification: test failure
Action: fix
Reason: fix-test
Prompt: fix_ci_failures.md
```

**Scenario 2: Mypy Errors**
```
Gate Status: failure
Failed Jobs: [mypy]
Classification: mypy failure
Action: fix
Reason: fix-mypy
Prompt: fix_ci_failures.md
```

**Scenario 3: Black Formatting**
```
Gate Status: failure
Failed Jobs: [lint (black)]
Classification: lint failure
Action: wait
Reason: gate-not-success
→ Autofix workflow handles this separately
```

**Scenario 4: All Passing**
```
Gate Status: success
Action: run
Reason: ready
Prompt: keepalive_next_task.md
```

### Consumer Setup

No additional configuration needed. The CI failure routing is built into the keepalive system and works automatically when you have:

1. `agents-keepalive-loop.yml` workflow
2. `pr-00-gate.yml` workflow (for gate status)
3. `fix_ci_failures.md` prompt (in `.github/codex/prompts/`)

Ensure `fix_ci_failures.md` exists in `.github/codex/prompts/` for fix mode to work properly.
