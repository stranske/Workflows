# Consumer Repo Workflow Templates
#
# These templates are designed to be copied to consumer repositories that want to use
# the centralized CI and automation workflows from stranske/Workflows.
#
# ## Quick Start
#
# 1. Copy the relevant workflow files to your repo's `.github/workflows/` directory
# 2. Configure required secrets in your repository settings
# 3. Adjust input parameters as needed
#
# ## Available Templates
#
# | File | Purpose | Required Secrets |
# |------|---------|-----------------|
# | `ci.yml` | Python CI (lint, format, tests, typecheck) | None |
# | `pr-00-gate.yml` | Gate workflow for merge enforcement | None |
# | `agents-issue-intake.yml` | Assigns agents to issues | `SERVICE_BOT_PAT`, `OWNER_PR_PAT` |
# | `agents-orchestrator.yml` | Scheduled keepalive sweeps | `SERVICE_BOT_PAT`, `ACTIONS_BOT_PAT` |
# | `agents-pr-meta.yml` | PR keepalive detection | `SERVICE_BOT_PAT`, `ACTIONS_BOT_PAT` |
# | `autofix.yml` | Auto-fix lint/format issues | `SERVICE_BOT_PAT` |
# | `autofix-versions.env` | Pin tool versions | N/A |
#
# ## Architecture
#
# These templates follow the "thin caller" pattern:
# - Triggers and permissions are defined locally (required by GitHub)
# - All logic is delegated to reusable workflows in stranske/Workflows
# - Consumer repos must include scripts required by `reusable-10-ci-python.yml`
#   - `scripts/sync_test_dependencies.py`
#   - `tools/resolve_mypy_pin.py`
#
# ## Required CI Scripts (Consumer Repos)
#
# The reusable Python CI workflow runs two scripts from the consumer repo.
# Add them before enabling `ci.yml` or the workflow will fail.
#
# 1. Create the folders if they do not exist:
#    - `scripts/`
#    - `tools/`
# 2. Copy the reference scripts into your repo:
#    - `templates/consumer-repo/scripts/sync_test_dependencies.py` → `scripts/sync_test_dependencies.py`
#    - `templates/consumer-repo/tools/resolve_mypy_pin.py` → `tools/resolve_mypy_pin.py`
#
# If you already use the integration repo template, you can copy the same files from:
# - `templates/integration-repo/scripts/sync_test_dependencies.py`
# - `templates/integration-repo/tools/resolve_mypy_pin.py`
#
# ## Security Note: Workflow Pinning
#
# These templates use `@main` for workflow references (e.g., `stranske/Workflows/...@main`).
# This is intentional for first-party consumer repos owned by the same account, allowing
# automatic updates without PR churn.
#
# **For third-party or security-sensitive deployments:**
# - Pin to a specific commit SHA: `@abc123def456...`
# - Or use version tags: `@v1` (points to latest v1.x release)
#
# ## Secret Requirements
#
# | Secret | Purpose | Who provides |
# |--------|---------|--------------|
# | `SERVICE_BOT_PAT` | Bot account for comments/labels | stranske-automation-bot |
# | `ACTIONS_BOT_PAT` | Workflow dispatch triggers | Account with actions:write |
# | `OWNER_PR_PAT` | Create PRs on behalf of user | Repository owner |
#
# ## Repository Variables
#
# | Variable | Purpose | Default |
# |----------|---------|---------|
# | `ALLOWED_KEEPALIVE_LOGINS` | Comma-separated list of users allowed to trigger keepalive | `stranske` |
#
# ## Customization
#
# Most templates accept inputs that can be customized:
# - Change schedule timing in orchestrator
# - Adjust label patterns for agent assignment
# - Configure autofix commit prefixes and labels
#
# See each template file for available options.
