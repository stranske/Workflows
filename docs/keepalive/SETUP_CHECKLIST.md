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

### Step 5: Create Required Secrets

Navigate to **Settings** → **Secrets and variables** → **Actions** → **Secrets** tab

#### Required Secrets:

| Secret Name | Purpose | How to Create |
|-------------|---------|---------------|
| `SERVICE_BOT_PAT` | Bot account PAT for agent actions | Create from bot account with `repo`, `workflow` scopes |
| `ACTIONS_BOT_PAT` | Alternative bot PAT (if using separate bot) | Same scopes as SERVICE_BOT_PAT |
| `OWNER_PR_PAT` | Owner PAT for PR operations | Create from your account with `repo` scope |

#### Creating SERVICE_BOT_PAT (Critical):

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

### Step 6: Create Repository Variables (Optional)

Navigate to **Settings** → **Secrets and variables** → **Actions** → **Variables** tab

| Variable Name | Purpose | Example Value |
|--------------|---------|---------------|
| `PRIMARY_PYTHON` | Default Python version | `3.13` |
| `COVERAGE_THRESHOLD` | Minimum coverage % | `80` |

---

## Branch Protection Rules

### Step 7: Protect Main Branch

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

### Step 8: Create Directory Structure

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
└── parse_chatgpt_topics.py
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

### Step 9: Copy Essential Files

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

#### Templates (`.github/templates/`)

- [ ] `keepalive-instruction.md` - Keepalive comment template

---

## Workflow Configuration

### Step 10: Configure Workflow Files

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
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main
    with:
      python_versions: '["3.11", "3.12", "3.13"]'
      primary_version: "3.13"
      min_coverage: 80
      fail_under_coverage: true
      ruff_check: true
      mypy_check: true
      strict_mypy: true
    secrets:
      token: ${{ secrets.SERVICE_BOT_PAT }}

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
  workflow_dispatch:

jobs:
  ci:
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main
    with:
      python_versions: '["3.11", "3.12", "3.13"]'
      primary_version: "3.13"
      min_coverage: 80
    secrets:
      token: ${{ secrets.SERVICE_BOT_PAT }}
```

#### C. Agent Workflows (if using keepalive)

- [ ] Copy `agents-pr-meta.yml` from templates
- [ ] Copy `agents-63-issue-intake.yml` from templates
- [ ] Copy `agents-70-orchestrator.yml` from templates

**Critical**: Ensure `agents-pr-meta.yml` includes the `fromJSON()` fix:

```yaml
pr_number: ${{ fromJSON(needs.detect.outputs.pr_number) }}
```

### Step 11: Configure pyproject.toml

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

### Step 12: Create Issues.txt

```text
# Issues.txt - Agent Issue Queue
# Format: One issue title per line
# Lines starting with # are comments
# Lines with [ ] or [x] are checkboxes (preserved)

- [ ] Set up project structure and basic tests
- [ ] Implement core functionality
```

### Step 13: Create Topics.txt

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

category: maintenance
- Dependency updates
- Code cleanup
- Performance optimization
```

---

## Verification Steps

### Step 14: Verify Workflow Access

1. [ ] Go to **Actions** tab
2. [ ] Confirm "I understand my workflows, go ahead and enable them" if prompted
3. [ ] Verify no workflow errors in the list

### Step 15: Create Test PR

1. [ ] Create a new branch: `git checkout -b test/initial-setup`
2. [ ] Make a small change (e.g., update README)
3. [ ] Push and create PR
4. [ ] Verify Gate workflow triggers
5. [ ] Verify CI checks run
6. [ ] Verify status checks appear on PR

### Step 16: Verify Agent Automation (if using keepalive)

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
| Basic CI | `SERVICE_BOT_PAT` |
| Full Agents | `SERVICE_BOT_PAT`, `ACTIONS_BOT_PAT` (optional), `OWNER_PR_PAT` (optional) |

---

*Last updated: Based on Travel-Plan-Permission PR analysis (PRs #47, #50, #64, #66, #71)*
