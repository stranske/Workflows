# Consumer Repo Setup Checklist

This document provides step-by-step instructions for setting up a new consumer repository that integrates with the stranske/Workflows reusable workflow system, including full keepalive agent automation.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Repository Creation](#repository-creation)
3. [Repository Settings](#repository-settings)
4. [Secrets Configuration](#secrets-configuration)
5. [Branch Protection Rules](#branch-protection-rules)
6. [File Structure Setup](#file-structure-setup)
7. [Workflow Configuration](#workflow-configuration)
8. [Verification Steps](#verification-steps)
9. [Troubleshooting](#troubleshooting)

---

## Prerequisites

Before beginning, ensure you have:

- [ ] GitHub account with access to create repositories
- [ ] Access to `stranske/Workflows` repository (for reusable workflows)
- [ ] Access to a GitHub bot account (e.g., `stranske-bot`) for SERVICE_BOT_PAT
- [ ] Codex CLI access (if using keepalive agent automation)

---

## Repository Creation

### Step 1: Create the Repository

1. [ ] Go to GitHub → New Repository
2. [ ] Set repository name (e.g., `My-Project`)
3. [ ] Set visibility: **Public** (required for Codex agents)
4. [ ] Initialize with README: **Yes**
5. [ ] Add .gitignore: **Python**
6. [ ] Add license: Choose appropriate license
7. [ ] Click **Create repository**

### Step 2: Enable GitHub Actions

1. [ ] Go to **Settings** → **Actions** → **General**
2. [ ] Under "Actions permissions", select: **Allow all actions and reusable workflows**
3. [ ] Under "Workflow permissions", select: **Read and write permissions**
4. [ ] Check: **Allow GitHub Actions to create and approve pull requests**
5. [ ] Click **Save**

---

## Repository Settings

### Step 3: Configure General Settings

1. [ ] Go to **Settings** → **General**
2. [ ] Under "Features":
   - [ ] Enable **Issues**
   - [ ] Enable **Projects** (optional)
   - [ ] Disable **Wiki** (optional)
3. [ ] Under "Pull Requests":
   - [ ] Enable **Allow merge commits**
   - [ ] Enable **Allow squash merging** (recommended default)
   - [ ] Enable **Automatically delete head branches**
4. [ ] Click **Save**

### Step 4: Configure Issue Settings

1. [ ] Go to **Settings** → **General** → scroll to "Features"
2. [ ] Click **Set up templates** next to Issues
3. [ ] Add issue templates as needed (optional but recommended)

---

## Secrets Configuration

### Step 5: Install Workflows GitHub App (Recommended)

The Workflows GitHub App provides secure, scoped authentication without personal tokens.

#### Install the App:

1. [ ] Contact repository owner for Workflows App installation link
2. [ ] Or create your own GitHub App with these permissions:
   - **Contents**: Read and write
   - **Issues**: Read and write  
   - **Pull requests**: Read and write
   - **Workflows**: Read and write
   - **Metadata**: Read (auto-selected)
3. [ ] Install App on your consumer repository

#### Configure App Secrets:

Navigate to **Settings** → **Secrets and variables** → **Actions** → **Secrets** tab

1. [ ] Get **App ID** from App settings page (numeric ID)
2. [ ] **Generate Private Key** from App settings (downloads `.pem` file)
3. [ ] Add secrets:
   - Name: `WORKFLOWS_APP_ID`
   - Value: The numeric App ID
   - Name: `WORKFLOWS_APP_PRIVATE_KEY`  
   - Value: Contents of the `.pem` file (entire file, including `-----BEGIN/END-----` lines)

> **Why use GitHub App?** Apps have repository-scoped permissions, don't count against user API limits, and don't expire like PATs. Workflows automatically fall back to PAT if App secrets aren't configured.

### Step 6: Create PAT Secrets (Fallback)

If not using GitHub App, create Personal Access Token secrets:

Navigate to **Settings** → **Secrets and variables** → **Actions** → **Secrets** tab

#### Required Secrets:

| Secret Name | Purpose | How to Create |
|-------------|---------|---------------|
| `SERVICE_BOT_PAT` | Bot account PAT for agent actions | Create from bot account with `repo`, `workflow` scopes |
| `ACTIONS_BOT_PAT` | Alternative bot PAT (if using separate bot) | Same scopes as SERVICE_BOT_PAT |
| `OWNER_PR_PAT` | Owner PAT for PR operations | Create from your account with `repo` scope |

#### Creating SERVICE_BOT_PAT:

1. [ ] Log into bot account (e.g., `stranske-bot`)
2. [ ] Go to **Settings** → **Developer settings** → **Personal access tokens** → **Fine-grained tokens**
3. [ ] Click **Generate new token**
4. [ ] Set name: `SERVICE_BOT_PAT for <repo-name>`
5. [ ] Set expiration: 90 days (or custom)
6. [ ] Repository access: **Only select repositories** → select your consumer repo
7. [ ] Permissions:
   - [ ] **Contents**: Read and write
   - [ ] **Issues**: Read and write
   - [ ] **Pull requests**: Read and write
   - [ ] **Workflows**: Read and write
   - [ ] **Metadata**: Read (auto-selected)
8. [ ] Click **Generate token**
9. [ ] Copy the token immediately
10. [ ] Add as repository secret: **Settings** → **Secrets** → **New repository secret**
    - Name: `SERVICE_BOT_PAT`
    - Value: (paste token)

### Step 7: Create Repository Variables (Optional)

Navigate to **Settings** → **Secrets and variables** → **Actions** → **Variables** tab

| Variable Name | Purpose | Example Value |
|--------------|---------|---------------|
| `PRIMARY_PYTHON` | Default Python version | `3.13` |
| `COVERAGE_THRESHOLD` | Minimum coverage % | `80` |
| `WORKFLOW_TIMEOUT_DEFAULT` | Default keepalive timeout (minutes) | `45` |
| `WORKFLOW_TIMEOUT_EXTENDED` | Extended keepalive timeout (minutes) | `90` |
| `WORKFLOW_TIMEOUT_WARNING_RATIO` | Timeout warning threshold (0-1) | `0.8` |
| `WORKFLOW_TIMEOUT_WARNING_MINUTES` | Timeout warning minimum minutes remaining | `5` |

#### Keepalive Timeout Configuration

- `WORKFLOW_TIMEOUT_DEFAULT` controls the base timeout used by keepalive runs.
- `WORKFLOW_TIMEOUT_EXTENDED` applies when a PR has the `timeout:extended` label.
- `WORKFLOW_TIMEOUT_WARNING_RATIO` triggers a warning when the elapsed ratio is met.
- `WORKFLOW_TIMEOUT_WARNING_MINUTES` triggers a warning when remaining minutes are low.
- Manual runs can override values with workflow inputs:
  - `timeout_minutes` to set the full timeout for the run.
  - `timeout_warning_ratio` to change the usage warning threshold.
  - `timeout_warning_minutes` to change the remaining-minutes warning threshold.

Example override payload:

```yaml
timeout_minutes: 75
timeout_warning_ratio: 0.8
timeout_warning_minutes: 10
```

---

## Branch Protection Rules

### Step 8: Protect Main Branch

1. [ ] Go to **Settings** → **Branches**
2. [ ] Click **Add branch protection rule**
3. [ ] Branch name pattern: `main`
4. [ ] Configure:
   - [ ] **Require a pull request before merging**
     - [ ] Require approvals: `1` (optional)
     - [ ] Dismiss stale PR approvals when new commits are pushed
   - [ ] **Require status checks to pass before merging**
     - [ ] Require branches to be up to date before merging
     - [ ] Status checks: Add `Gate` (after first workflow run)
   - [ ] **Do not allow bypassing the above settings** (optional)
5. [ ] Click **Create** or **Save changes**

> **Note**: The `Gate` status check won't be available until after the first PR workflow runs successfully.

---

## File Structure Setup

### Step 8: Update .gitignore

Copy the workflow-generated file patterns from the canonical template to prevent merge conflicts.

#### Option A: Copy from Template (Recommended)

Copy the entire "Workflows Consumer Repo - Shared Status Files" section from:
```
stranske/Workflows/templates/consumer-repo/.gitignore
```

This includes all patterns for:
- Agent working files (codex-prompt.md, verifier-context.md, etc.)
- Autofix status files (autofix_report_enriched.json, ci/autofix/*.json)
- Metrics/history files (keepalive_status.md, *-history.ndjson, etc.)
- Build artifacts (.autofix-venv/)
- PR automation files (pr_body.md)
- And more

#### Option B: Validate with Script

Use the sync script to check your .gitignore coverage:

```bash
# Check what patterns are missing
python scripts/sync_status_file_ignores.py --check

# Print the canonical block to copy
python scripts/sync_status_file_ignores.py --print-block
```

> **Why this matters**: When multiple PRs run keepalive concurrently, each
> generates these working files. Without these patterns, files get tracked
> and cause merge conflicts when agents try to update branches (see
> stranske/Trend_Model_Project#4355). Historical data is preserved in PR
> comments and workflow artifacts, not git history.

> **Maintainability**: Don't copy individual patterns - reference the template
> or use the validation script. The canonical list is maintained in one place
> and consumer repos stay in sync.

### Step 10: Create Directory Structure

Create the following directory structure:

```
.github/
├── scripts/                    # Agent JavaScript utilities
│   ├── issue_context_utils.js
│   ├── issue_pr_locator.js
│   ├── issue_scope_parser.js
│   └── keepalive_instruction_template.js
├── templates/
│   └── keepalive-instruction.md
└── workflows/
    ├── agents-63-issue-intake.yml
    ├── agents-70-orchestrator.yml
    ├── agents-pr-meta.yml
    ├── autofix.yml
    ├── ci.yml
    └── pr-00-gate.yml
scripts/                        # Python utility scripts
├── decode_raw_input.py
├── fallback_split.py
├── parse_chatgpt_topics.py
└── sync_test_dependencies.py
tools/                          # CI helper scripts for reusable workflows
└── resolve_mypy_pin.py
src/
└── my_project/                 # Your Python package
    ├── __init__.py
    └── main.py
tests/
├── __init__.py
└── test_main.py
Issues.txt                      # Agent issue queue
Topics.txt                      # Issue topic configuration
pyproject.toml                  # Python project configuration
README.md
```

### Step 11: Copy Essential Files

#### JavaScript Agent Scripts (`.github/scripts/`)

Copy from Travel-Plan-Permission or use the templates:

- [ ] `issue_pr_locator.js` - Locates related PRs for issues
- [ ] `issue_context_utils.js` - Context gathering utilities
- [ ] `issue_scope_parser.js` - Parses issue scope from text
- [ ] `keepalive_instruction_template.js` - Generates keepalive instructions

#### Python Utility Scripts (`scripts/`)

- [ ] `decode_raw_input.py` - Decodes base64 input
- [ ] `parse_chatgpt_topics.py` - Parses Topics.txt format
- [ ] `fallback_split.py` - Splits large issues into subtasks

#### CI Scripts Required by `reusable-10-ci-python.yml`

Add these files or CI will fail when the reusable Python workflow runs:

- [ ] `scripts/sync_test_dependencies.py` - Checks test imports vs dev dependencies
- [ ] `tools/resolve_mypy_pin.py` - Selects the Python version used by mypy

Copy from:

- [ ] `templates/consumer-repo/scripts/sync_test_dependencies.py`
- [ ] `templates/consumer-repo/tools/resolve_mypy_pin.py`

#### Templates (`.github/templates/`)

- [ ] `keepalive-instruction.md` - Keepalive comment template

---


---

## 📌 Important: Template Sync Process

Before configuring workflows, understand how this consumer repo receives updates:

### How Workflow Updates Work

1. **Source**: Workflow scripts live in `stranske/Workflows/templates/consumer-repo/`
2. **Sync**: The Workflows repo has a sync process that creates PRs to update consumer repos
3. **Trigger**: Sync happens when template files change or on manual trigger

### Template Sync Validation (For Workflows Repo Contributors)

If you're contributing to the Workflows repo and modifying `.github/scripts/`:

```bash
# After editing workflow scripts
./scripts/sync_templates.sh

# Verify templates are in sync
python scripts/validate_template_sync.py
```

**Why this matters**: Consumer repos only get updates when template files change. If you modify `.github/scripts/` but forget to update `templates/consumer-repo/.github/scripts/`, no sync PRs are created.

The CI enforces this with `.github/workflows/health-72-template-sync.yml`.

### As a Consumer Repo User

- Watch for sync PRs from the Workflows repo
- Review and merge them to get the latest workflow improvements
- Don't manually edit workflow files in `.github/workflows/` or `.github/scripts/` - changes will be overwritten on next sync

---

## Workflow Configuration

### Step 12: Configure Workflow Files

#### A. Gate Workflow (`pr-00-gate.yml`)

```yaml
name: Gate

on:
  pull_request:
    branches: [main]
  workflow_run:
    workflows: ["CI", "Autofix"]
    types: [completed]
    branches-ignore: [main]

jobs:
  python-ci:
    if: github.event_name == 'pull_request'
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@v1
    with:
      python-versions: '["3.11", "3.12", "3.13"]'
      primary-python-version: "3.13"
      coverage-min: "80"
    secrets: inherit

  gate-summary:
    needs: [python-ci]
    if: always()
    runs-on: ubuntu-latest
    steps:
      - name: Gate Summary
        run: |
          if [[ "${{ needs.python-ci.result }}" == "success" ]]; then
            echo "✅ All checks passed"
          else
            echo "❌ Some checks failed"
            exit 1
          fi
```

#### B. CI Workflow (`ci.yml`)

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  ci:
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@v1
    with:
      python-versions: '["3.11", "3.12", "3.13"]'
      primary-python-version: "3.13"
      coverage-min: "80"
    secrets: inherit
```

#### C. Autofix Workflow (`autofix.yml`)

```yaml
name: Autofix

on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  autofix:
    uses: stranske/Workflows/.github/workflows/reusable-11-autofix-python.yml@v1
    secrets: inherit
```

> Autofix automatically formats code and fixes linting issues when Gate fails.

#### D. Agent Workflows (if using keepalive)

- [ ] Copy `agents-pr-meta.yml` from templates
- [ ] Copy `agents-63-issue-intake.yml` from templates
- [ ] Copy `agents-70-orchestrator.yml` from templates

**Critical**: Ensure `agents-pr-meta.yml` includes the `fromJSON()` fix:

```yaml
pr_number: ${{ fromJSON(needs.detect.outputs.pr_number) }}
```

### Step 13: Configure pyproject.toml

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "my-project"
version = "0.1.0"
description = "My project description"
readme = "README.md"
requires-python = ">=3.11"
dependencies = []

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=4.0",
    "ruff>=0.4",
    "mypy>=1.10",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --cov=src --cov-report=term-missing"

[tool.ruff]
target-version = "py311"
line-length = 88
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "B", "C4", "SIM"]

[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_configs = true
```

### Step 14: Configure Issue Sources (For Agent Automation)

If using `agents-issue-intake.yml` workflow, create these files:

#### Issues.txt

Lists GitHub issues to auto-create in your repo:

```text
# Issues.txt - Agent Issue Queue
# Format: owner/repo#issue_number
# One issue per line, comments start with #

stranske/Workflows#123
stranske/Trend_Model_Project#456
```

> Issues listed here will be cloned into your repository with the `agent:codex` label.

#### Topics.txt

ChatGPT-generated topic breakdown for batch issue creation:

```text
# Topics.txt - Issue Topic Configuration
# Used by agents to categorize and route issues

category: setup
- Project scaffolding
- CI/CD configuration
- Documentation

category: features
- Core functionality
- API endpoints
- Data processing
```

> **Note**: Both files are optional. You can also create issues manually and apply the `agent:codex` or `agent:copilot` labels.

### Step 15: Configure Agent Labels

Create these labels in **Settings** → **Labels**:

| Label | Color | Description |
|-------|-------|-------------|
| `agent:codex` | `#0E8A16` | Assigns work to Codex agent |
| `agent:copilot` | `#1D76DB` | Assigns work to Copilot agent |
| `agents:paused` | `#D93F0B` | Pauses agent automation |
| `agents:debug` | `#FBCA04` | Enables debug logging and escalation comments |
| `autofix-exempt` | `#EDEDED` | Skips autofix attempts on this PR |
| `gate-exempt` | `#EDEDED` | Allows merge without passing Gate checks |

> The `agents-auto-label.yml` workflow can suggest additional labels based on issue content using semantic matching.

### Step 16: Understand the Sync System

Consumer repos receive automatic updates from Workflows via `maint-68-sync-consumer-repos.yml`.

#### What Gets Synced

The sync manifest (`.github/sync-manifest.yml` in Workflows) declares which files sync:

- ✅ `.github/workflows/` - Agent and CI workflows
- ✅ `.github/scripts/` - JavaScript utilities  
- ✅ `.github/templates/` - Prompt templates
- ✅ Some `scripts/` files - Python utilities (listed in manifest)
- ✅ `tools/` - CI helper scripts
- ❌ `.gitignore` - Repo-specific (never synced)
- ❌ `pyproject.toml` - Repo-specific
- ❌ `README.md` - Repo-specific
- ❌ `scripts/langchain/` - Use sparse checkout instead

#### Handling Sync PRs

When Workflows updates, you'll get a PR with title like `chore: sync from Workflows`.

**Option A - Automatic** (Recommended): The `maint-71-merge-sync-prs.yml` workflow in Workflows can auto-merge these PRs after CI passes.

**Option B - Manual**: Review and merge normally:
```bash
gh pr merge <pr-number> --squash --auto
```

> **Important**: Files marked `sync_mode: create_only` in the manifest (like `pr-00-gate.yml` and `ci.yml`) won't be overwritten by sync. You maintain control over customizations like coverage thresholds and Python versions.

#### When Sync Fails

If a sync PR has conflicts:
1. The sync workflow will comment on the PR with conflict details
2. You can resolve conflicts manually or let the agent handle it
3. Check `.github/sync-manifest.yml` in Workflows to see what's expected

---

## Verification Steps

### Step 17: Verify Workflow Access

1. [ ] Go to **Actions** tab
2. [ ] Confirm "I understand my workflows, go ahead and enable them" if prompted
3. [ ] Verify no workflow errors in the list

### Step 18: Create Test PR

1. [ ] Create a new branch: `git checkout -b test/initial-setup`
2. [ ] Make a small change (e.g., update README)
3. [ ] Push and create PR
4. [ ] Verify Gate workflow triggers
5. [ ] Verify CI checks run
6. [ ] Verify Autofix workflow triggers if there are linting issues
7. [ ] Verify status checks appear on PR

### Step 19: Verify Agent Automation (if using keepalive)

1. [ ] Ensure Issues.txt has at least one issue
2. [ ] Manually trigger `agents-63-issue-intake.yml` via Actions tab
3. [ ] Verify issue is created in Issues tab
4. [ ] Verify orchestrator workflow triggers
5. [ ] Check for keepalive comment on any agent-created PR

#### Verification Commands

Run these in your local clone to verify scripts exist:

```bash
# Check JavaScript scripts
ls -la .github/scripts/

# Check Python scripts
ls -la scripts/

# Check workflows
ls -la .github/workflows/

# Check template
ls -la .github/templates/
```

---

## Troubleshooting

### Common Issues

| Symptom | Cause | Solution |
|---------|-------|----------|
| Gate workflow doesn't trigger | Missing `workflow_run` trigger | Add workflow_run trigger for CI and Autofix |
| PR status not updating | Missing commit status step | Add uses-commit-status in Gate workflow |
| Keepalive not detecting PRs | `pr_number` type mismatch | Use `fromJSON(needs.detect.outputs.pr_number)` |
| Agent can't push to PR | Insufficient PAT permissions | Verify SERVICE_BOT_PAT has `contents: write` |
| Artifact 409 conflict | Duplicate artifact names on retry | Ensure artifact names include `${{ github.run_attempt }}` |

### Debug Checklist

- [ ] Check Actions tab for workflow run errors
- [ ] Verify secrets are correctly named and have values
- [ ] Verify PAT hasn't expired
- [ ] Check branch protection isn't blocking pushes
- [ ] Review workflow YAML for syntax errors

### Getting Help

1. Review [KEEPALIVE_TROUBLESHOOTING.md](KEEPALIVE_TROUBLESHOOTING.md) for agent-specific issues
2. Check [stranske/Workflows](https://github.com/stranske/Workflows) documentation
3. Open an issue in the Workflows repository

---

## Quick Reference

### Minimum Viable Setup (No Agents)

Just need CI? Copy these files:
- `.github/workflows/pr-00-gate.yml`
- `.github/workflows/ci.yml`
- `pyproject.toml`

### Full Agent Setup

Need keepalive automation? Also copy:
- `.github/workflows/agents-*.yml` (all agent workflows)
- `.github/scripts/` (all JS files)
- `scripts/` (Python utilities)
- `.github/templates/keepalive-instruction.md`
- `Issues.txt`
- `Topics.txt`

### Required Secrets Summary

| Setup Type | Required Secrets |
|------------|------------------|
| Basic CI | `WORKFLOWS_APP_ID` + `WORKFLOWS_APP_PRIVATE_KEY` (recommended) OR `SERVICE_BOT_PAT` (fallback) |
| Full Agents | GitHub App (recommended) OR `SERVICE_BOT_PAT`, `ACTIONS_BOT_PAT` (optional), `OWNER_PR_PAT` (optional) |

> **Recommendation**: Use GitHub App authentication (Step 5) for better security, scoped permissions, and no API rate limits. PATs are supported as fallback.

---

*Last updated: Based on Travel-Plan-Permission PR analysis (PRs #47, #50, #64, #66, #71)*
