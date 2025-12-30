# Trend_Model_Project Transition Plan

> **Document**: Comprehensive plan to migrate TMP to the stranske/Workflows consumer pattern
> **Date**: 2025-12-30
> **Branch**: codex/issue-297

## Executive Summary

This document details the transition of **Trend_Model_Project (TMP)** from its current
standalone workflow system to the centralized **stranske/Workflows** consumer pattern.
TMP already has extensive CI automation built locally; this transition will replace those
local workflows with thin caller workflows that reference the centralized reusable
workflows, bringing consistency with Manager-Database and Travel-Plan-Permission.

### Key Differences from Fresh Consumer Setup

- TMP has **existing workflows** that served as templates for the Workflows repo
- TMP already has **Gate / gate** branch protection configured
- TMP has **sophisticated local automation** that will be archived, not deleted
- GitHub App secrets (`WORKFLOWS_APP_ID`, `WORKFLOWS_APP_PRIVATE_KEY`) should be
  configured as the **preferred** authentication method (fallback to PAT-based)

---

## Pre-Transition Assessment

### Current TMP Workflow Inventory (to archive)

Based on TMP analysis, these local workflows exist and should be archived:

| Category | Workflow Files | Notes |
|----------|---------------|-------|
| **Gate** | `pr-00-gate.yml` | Local implementation - replace with consumer caller |
| **Agents** | `agents-63-issue-intake.yml`, `agents-64-*`, `agents-70-*`, `agents-71-*`, `agents-72-*`, `agents-73-*` | Replace with thin callers |
| **Autofix** | `autofix.yml`, `reusable-18-autofix.yml` | Replace with caller to Workflows |
| **Reusables** | `reusable-10-ci-python.yml`, `reusable-12-ci-docker.yml`, `reusable-16-agents.yml` | DELETE - will call central versions |
| **Health** | `health-40-*`, `health-41-*`, `health-42-*`, `health-43-*`, `health-44-*` | Keep if TMP-specific; review needed |
| **Maint** | `maint-45-*`, `maint-47-*`, `maint-50-*`, `maint-51-*`, `maint-52-*`, `maint-60-*` | Archive - not part of consumer pattern |

### What TMP Already Has (no changes needed)

- [x] Branch protection requiring `Gate / gate` status
- [x] Repository secrets available (SERVICE_BOT_PAT, ACTIONS_BOT_PAT, OWNER_PR_PAT, CODEX_AUTH_JSON)
- [x] GitHub App configured (WORKFLOWS_APP_ID, WORKFLOWS_APP_PRIVATE_KEY) - **NEW preferred auth**

---

## Phase 0: Archive Existing Workflows

**Purpose**: Preserve existing work before replacement.

### 0.1 Create Archive Directory

```bash
cd /path/to/Trend_Model_Project
mkdir -p archives/github-actions/2025-12-30-pre-workflows-migration/
```

### 0.2 Archive Local Workflows

```bash
# Move ALL local reusable workflows (these become remote calls)
mv .github/workflows/reusable-*.yml archives/github-actions/2025-12-30-pre-workflows-migration/

# Archive local agent implementations
for f in .github/workflows/agents-*.yml; do
  [ -f "$f" ] && mv "$f" archives/github-actions/2025-12-30-pre-workflows-migration/
done

# Archive autofix
mv .github/workflows/autofix.yml archives/github-actions/2025-12-30-pre-workflows-migration/

# Archive health workflows (unless TMP-specific customization exists)
for f in .github/workflows/health-*.yml; do
  [ -f "$f" ] && mv "$f" archives/github-actions/2025-12-30-pre-workflows-migration/
done

# Archive maintenance workflows
for f in .github/workflows/maint-*.yml; do
  [ -f "$f" ] && mv "$f" archives/github-actions/2025-12-30-pre-workflows-migration/
done

# Archive Gate (will be replaced with consumer version)
mv .github/workflows/pr-00-gate.yml archives/github-actions/2025-12-30-pre-workflows-migration/
```

### 0.3 Document Archive

Create `archives/github-actions/2025-12-30-pre-workflows-migration/README.md`:

```markdown
# Pre-Workflows Migration Archive

**Date**: 2025-12-30
**Reason**: Transition to stranske/Workflows consumer pattern

## Contents

These workflows were archived during the transition from local implementations
to the centralized stranske/Workflows consumer pattern.

## Recovery

If needed, these files can be restored from this archive or git history.
The new consumer pattern uses thin caller workflows that reference
`stranske/Workflows/.github/workflows/reusable-*.yml@main`.
```

---

## Phase 1: Create Required Labels

**Purpose**: Ensure all automation labels exist.

### 1.1 Required Labels

Run this script or create labels manually:

```bash
#!/bin/bash
# create-labels.sh

REPO="stranske/Trend_Model_Project"

labels=(
  "agent:codex|0366d6|Assigns Codex agent to issue"
  "agent:needs-attention|d93f0b|Agent needs human intervention"
  "agents:keepalive|1d76db|Enables keepalive automation"
  "autofix|0e8a16|Triggers automated code fixes"
  "autofix:clean|c5def5|Triggers clean-mode autofix"
  "autofix:applied|bfdadc|Autofix was applied"
  "autofix:clean-only|fbca04|Only tests-only cosmetic fixes"
  "status:ready|28a745|Issue ready for agent processing"
  "status:in-progress|f9d0c4|Agent is actively working"
)

for label_spec in "${labels[@]}"; do
  IFS='|' read -r name color description <<< "$label_spec"
  gh label create "$name" --color "$color" --description "$description" --repo "$REPO" 2>/dev/null || \
    gh label edit "$name" --color "$color" --description "$description" --repo "$REPO" 2>/dev/null || \
    echo "Label $name already exists"
done
```

### 1.2 Validation

- [ ] `agent:codex` label exists (blue)
- [ ] `agent:needs-attention` label exists (orange)
- [ ] `agents:keepalive` label exists (blue)
- [ ] `autofix` label exists (green)
- [ ] `autofix:clean` label exists (light purple)
- [ ] `autofix:applied` label exists (pink)
- [ ] `autofix:clean-only` label exists (yellow)
- [ ] `status:ready` label exists (green)
- [ ] `status:in-progress` label exists (salmon)

---

## Phase 2: Configure Secrets and Variables

**Purpose**: Ensure all authentication and configuration is in place.

### 2.1 Required Secrets

Navigate: **Settings** → **Secrets and variables** → **Actions** → **Secrets**

| Secret | Description | Status |
|--------|-------------|--------|
| `SERVICE_BOT_PAT` | PAT for service bot | ✅ Already configured |
| `ACTIONS_BOT_PAT` | PAT for workflow dispatch | ✅ Already configured |
| `OWNER_PR_PAT` | PAT for PR creation | ✅ Already configured |
| `CODEX_AUTH_JSON` | Codex CLI auth | ✅ Already configured |
| `WORKFLOWS_APP_ID` | GitHub App ID | 🆕 **Configure from App** |
| `WORKFLOWS_APP_PRIVATE_KEY` | GitHub App private key | 🆕 **Configure from App** |

### 2.2 GitHub App Configuration (Preferred Method)

The GitHub App provides secure, scoped authentication without personal tokens.

1. **Get App ID**: From App settings page
2. **Generate Private Key**: Download `.pem` file from App settings
3. **Add Secrets**:
   - `WORKFLOWS_APP_ID`: The numeric App ID
   - `WORKFLOWS_APP_PRIVATE_KEY`: Contents of the `.pem` file

> **Fallback**: If App secrets are not configured, workflows will fall back to
> `ACTIONS_BOT_PAT` / `SERVICE_BOT_PAT`.

### 2.3 Required Variables

Navigate: **Settings** → **Secrets and variables** → **Actions** → **Variables**

| Variable | Value | Description |
|----------|-------|-------------|
| `ALLOWED_KEEPALIVE_LOGINS` | `stranske` | Users who can trigger keepalive |

### 2.4 Validation Checklist

- [ ] All secrets configured
- [ ] `WORKFLOWS_APP_ID` configured (numeric)
- [ ] `WORKFLOWS_APP_PRIVATE_KEY` configured (PEM contents)
- [ ] `ALLOWED_KEEPALIVE_LOGINS` variable set

---

## Phase 3: Install Consumer Workflows

**Purpose**: Copy thin caller workflows that reference centralized reusable workflows.

### 3.1 Source Locations

Templates are in `stranske/Workflows/templates/consumer-repo/.github/workflows/`:

| Template | Purpose | Keepalive Critical |
|----------|---------|-------------------|
| `pr-00-gate.yml` | CI enforcement, commit status | **YES** |
| `ci.yml` | Thin Python CI caller | No |
| `agents-63-issue-intake.yml` | Full issue intake | No |
| `agents-bot-comment-handler.yml` | @codex comment handler | **YES** |
| `agents-keepalive-loop.yml` | Keepalive iteration | **YES** |
| `agents-orchestrator.yml` | Orchestrator entry point | **YES** |
| `agents-pr-meta.yml` | PR metadata/keepalive detection | **YES** |
| `agents-verifier.yml` | Post-merge verification | No |
| `agents-autofix-loop.yml` | Autofix automation | No |
| `autofix.yml` | Autofix workflow | No |
| `maint-coverage-guard.yml` | Coverage regression guard | Recommended |

### 3.2 Copy Commands

```bash
# From Workflows repo
cd /workspaces/Workflows

# Copy all consumer templates to TMP
DEST="/path/to/Trend_Model_Project/.github/workflows"

# Critical for keepalive
cp templates/consumer-repo/.github/workflows/pr-00-gate.yml "$DEST/"
cp templates/consumer-repo/.github/workflows/agents-bot-comment-handler.yml "$DEST/"
cp templates/consumer-repo/.github/workflows/agents-keepalive-loop.yml "$DEST/"
cp templates/consumer-repo/.github/workflows/agents-orchestrator.yml "$DEST/"
cp templates/consumer-repo/.github/workflows/agents-pr-meta.yml "$DEST/"

# Agent automation
cp templates/consumer-repo/.github/workflows/agents-63-issue-intake.yml "$DEST/"
cp templates/consumer-repo/.github/workflows/agents-verifier.yml "$DEST/"
cp templates/consumer-repo/.github/workflows/agents-autofix-loop.yml "$DEST/"

# CI
cp templates/consumer-repo/.github/workflows/ci.yml "$DEST/"
cp templates/consumer-repo/.github/workflows/autofix.yml "$DEST/"
cp templates/consumer-repo/.github/workflows/maint-coverage-guard.yml "$DEST/"
```

### 3.3 Critical Post-Copy Fixes

#### Fix `agents-63-issue-intake.yml` Reusable Reference

The source file has a LOCAL reference that must be changed to REMOTE:

```yaml
# ❌ WRONG (local reference - will fail in consumer repo)
uses: ./.github/workflows/reusable-agents-issue-bridge.yml

# ✅ CORRECT (remote reference)
uses: stranske/Workflows/.github/workflows/reusable-agents-issue-bridge.yml@main
```

**Find and replace** (approximately line 1171):
```bash
sed -i 's|uses: ./.github/workflows/reusable-agents-issue-bridge.yml|uses: stranske/Workflows/.github/workflows/reusable-agents-issue-bridge.yml@main|g' \
  "$DEST/agents-63-issue-intake.yml"
```

### 3.4 Create Autofix Versions File

Create `.github/workflows/autofix-versions.env`:

```bash
# Tool versions for autofix - match TMP's current lock files
RUFF_VERSION=0.8.1
MYPY_VERSION=1.14.0
BLACK_VERSION=24.10.0
ISORT_VERSION=5.13.2
```

> **Important**: Check TMP's `pyproject.toml` or `requirements*.txt` for actual versions.

### 3.5 Validation Checklist

- [ ] `pr-00-gate.yml` copied (uses `stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main`)
- [ ] `agents-keepalive-loop.yml` copied (uses `stranske/Workflows/.github/workflows/reusable-codex-run.yml@main`)
- [ ] `agents-orchestrator.yml` copied
- [ ] `agents-pr-meta.yml` copied
- [ ] `agents-bot-comment-handler.yml` copied
- [ ] `agents-63-issue-intake.yml` copied AND fixed (remote reference)
- [ ] `autofix-versions.env` created with correct versions
- [ ] All workflows reference `stranske/Workflows/...@main`

---

## Phase 4: Install Scripts and Prompts

**Purpose**: Copy supporting scripts and Codex prompts.

### 4.1 Required JavaScript Scripts

Copy to `.github/scripts/`:

```bash
SCRIPTS_DEST="/path/to/Trend_Model_Project/.github/scripts"
mkdir -p "$SCRIPTS_DEST"

# From Workflows repo
cp .github/scripts/issue_pr_locator.js "$SCRIPTS_DEST/"
cp .github/scripts/issue_context_utils.js "$SCRIPTS_DEST/"
cp .github/scripts/issue_scope_parser.js "$SCRIPTS_DEST/"
cp .github/scripts/keepalive_instruction_template.js "$SCRIPTS_DEST/"
```

### 4.2 Required Python Scripts

```bash
cp .github/scripts/decode_raw_input.py "$SCRIPTS_DEST/"
cp .github/scripts/parse_chatgpt_topics.py "$SCRIPTS_DEST/"
cp .github/scripts/fallback_split.py "$SCRIPTS_DEST/"
```

### 4.3 Codex Prompts

```bash
CODEX_DEST="/path/to/Trend_Model_Project/.github/codex"
mkdir -p "$CODEX_DEST/prompts"

cp .github/codex/AGENT_INSTRUCTIONS.md "$CODEX_DEST/"
cp .github/codex/prompts/keepalive_next_task.md "$CODEX_DEST/prompts/"
cp .github/codex/prompts/fix_ci_failures.md "$CODEX_DEST/prompts/"
```

### 4.4 Templates

```bash
TEMPLATES_DEST="/path/to/Trend_Model_Project/.github/templates"
mkdir -p "$TEMPLATES_DEST"

cp .github/templates/keepalive-instruction.md "$TEMPLATES_DEST/"
```

### 4.5 Validation Checklist

- [ ] `.github/scripts/issue_pr_locator.js` present
- [ ] `.github/scripts/issue_context_utils.js` present
- [ ] `.github/scripts/issue_scope_parser.js` present
- [ ] `.github/scripts/keepalive_instruction_template.js` present
- [ ] `.github/scripts/decode_raw_input.py` present
- [ ] `.github/scripts/parse_chatgpt_topics.py` present
- [ ] `.github/scripts/fallback_split.py` present
- [ ] `.github/codex/AGENT_INSTRUCTIONS.md` present
- [ ] `.github/codex/prompts/keepalive_next_task.md` present
- [ ] `.github/codex/prompts/fix_ci_failures.md` present
- [ ] `.github/templates/keepalive-instruction.md` present

---

## Phase 5: Verify and Test

**Purpose**: Validate the transition and confirm automation works.

### 5.1 Pre-Push Validation

```bash
# Validate YAML syntax
for f in .github/workflows/*.yml; do
  echo "Checking $f..."
  python -c "import yaml; yaml.safe_load(open('$f'))" || echo "INVALID: $f"
done

# Check for LOCAL references (should be none except specific patterns)
grep -r "uses: ./" .github/workflows/*.yml | grep -v "actions/" || echo "No local workflow references found (good)"

# Verify remote references point to stranske/Workflows
grep -r "stranske/Workflows" .github/workflows/*.yml | head -20
```

### 5.2 Create Test PR

1. Create a test branch:
   ```bash
   git checkout -b test/workflows-migration
   git add .
   git commit -m "chore: migrate to stranske/Workflows consumer pattern"
   git push -u origin test/workflows-migration
   ```

2. Open PR and verify:
   - [ ] Gate workflow runs
   - [ ] Gate posts `Gate / gate` commit status
   - [ ] CI completes (lint, type, test)
   - [ ] PR summary comment appears

### 5.3 Test Keepalive (after Gate passes)

1. Add `agents:keepalive` label to the PR
2. Post `@codex round 1` comment
3. Verify:
   - [ ] `agents-pr-meta.yml` detects the comment
   - [ ] `agents-keepalive-loop.yml` triggers
   - [ ] Codex runs (check Actions tab)

### 5.4 Test Issue Intake

1. Create test issue with `agent:codex` label
2. Verify:
   - [ ] `agents-63-issue-intake.yml` triggers
   - [ ] Bootstrap PR is created
   - [ ] Branch `codex/issue-<number>` exists

### 5.5 Compare with Reference Repos

When troubleshooting, compare with:
- `stranske/Travel-Plan-Permission` (reference consumer)
- `stranske/Manager-Database` (production consumer)
- `stranske/PAEM` (production consumer)

---

## Appendix A: Dual Checkout Pattern

Consumer workflows use a **dual checkout pattern** to access both:
1. The consumer repo (for context)
2. The Workflows repo scripts (for utilities)

Example from `agents-keepalive-loop.yml`:

```yaml
- name: Checkout consumer repo
  uses: actions/checkout@v4
  with:
    ref: ${{ inputs.pr_ref || github.ref }}
    fetch-depth: 0

- name: Checkout Workflows scripts
  uses: actions/checkout@v4
  with:
    repository: stranske/Workflows
    ref: main
    sparse-checkout: |
      scripts
      .github/scripts
    sparse-checkout-cone-mode: false
    path: workflows-lib
    token: ${{ env.CHECKOUT_TOKEN }}
```

Scripts are then accessed via `workflows-lib/scripts/`.

---

## Appendix B: GitHub App Token Flow

The preferred authentication uses GitHub App tokens:

```yaml
- name: Mint GitHub App token (preferred)
  id: app_token
  continue-on-error: true
  uses: actions/create-github-app-token@v1
  with:
    app-id: ${{ secrets.WORKFLOWS_APP_ID }}
    private-key: ${{ secrets.WORKFLOWS_APP_PRIVATE_KEY }}

- name: Select auth token
  id: auth_token
  run: |
    if [ -n "${{ steps.app_token.outputs.token }}" ]; then
      echo "token=${{ steps.app_token.outputs.token }}" >> "$GITHUB_OUTPUT"
      echo "source=app-token" >> "$GITHUB_OUTPUT"
    else
      echo "token=${{ secrets.ACTIONS_BOT_PAT }}" >> "$GITHUB_OUTPUT"
      echo "source=pat-fallback" >> "$GITHUB_OUTPUT"
    fi
```

---

## Appendix C: Troubleshooting

### Workflow fails with "workflow file not found"

- Consumer workflows call into `stranske/Workflows/.github/workflows/`
- Verify the reusable workflow exists in the Workflows repo
- Check the `@main` reference is correct

### Gate doesn't post commit status

- Verify `pr-00-gate.yml` has the commit status step
- Check permissions include `statuses: write`
- Verify `context: 'Gate / gate'` matches branch protection

### Keepalive doesn't trigger

- Check PR has `agents:keepalive` label
- Verify comment matches pattern `@codex round N`
- Check `agents-pr-meta.yml` has `workflow_run` trigger for Gate
- Confirm `ALLOWED_KEEPALIVE_LOGINS` includes the commenter

### Agent not picking up issues

- Verify `agent:codex` label is present
- Check issue has valid agent assignee
- Review `agents-63-issue-intake.yml` logs

---

## Appendix D: File Checklist Summary

### Workflows (`.github/workflows/`)

| File | Source | Status |
|------|--------|--------|
| `pr-00-gate.yml` | `templates/consumer-repo/.github/workflows/` | ⬜ |
| `ci.yml` | `templates/consumer-repo/.github/workflows/` | ⬜ |
| `autofix.yml` | `templates/consumer-repo/.github/workflows/` | ⬜ |
| `agents-63-issue-intake.yml` | `templates/consumer-repo/.github/workflows/` | ⬜ |
| `agents-bot-comment-handler.yml` | `templates/consumer-repo/.github/workflows/` | ⬜ |
| `agents-keepalive-loop.yml` | `templates/consumer-repo/.github/workflows/` | ⬜ |
| `agents-orchestrator.yml` | `templates/consumer-repo/.github/workflows/` | ⬜ |
| `agents-pr-meta.yml` | `templates/consumer-repo/.github/workflows/` | ⬜ |
| `agents-verifier.yml` | `templates/consumer-repo/.github/workflows/` | ⬜ |
| `agents-autofix-loop.yml` | `templates/consumer-repo/.github/workflows/` | ⬜ |
| `maint-coverage-guard.yml` | `templates/consumer-repo/.github/workflows/` | ⬜ |
| `autofix-versions.env` | Create manually | ⬜ |

### Scripts (`.github/scripts/`)

| File | Status |
|------|--------|
| `issue_pr_locator.js` | ⬜ |
| `issue_context_utils.js` | ⬜ |
| `issue_scope_parser.js` | ⬜ |
| `keepalive_instruction_template.js` | ⬜ |
| `decode_raw_input.py` | ⬜ |
| `parse_chatgpt_topics.py` | ⬜ |
| `fallback_split.py` | ⬜ |

### Codex (`.github/codex/`)

| File | Status |
|------|--------|
| `AGENT_INSTRUCTIONS.md` | ⬜ |
| `prompts/keepalive_next_task.md` | ⬜ |
| `prompts/fix_ci_failures.md` | ⬜ |

### Templates (`.github/templates/`)

| File | Status |
|------|--------|
| `keepalive-instruction.md` | ⬜ |

### Labels

| Label | Status |
|-------|--------|
| `agent:codex` | ⬜ |
| `agent:needs-attention` | ⬜ |
| `agents:keepalive` | ⬜ |
| `autofix` | ⬜ |
| `autofix:clean` | ⬜ |
| `autofix:applied` | ⬜ |
| `autofix:clean-only` | ⬜ |
| `status:ready` | ⬜ |
| `status:in-progress` | ⬜ |

### Secrets

| Secret | Status |
|--------|--------|
| `SERVICE_BOT_PAT` | ✅ |
| `ACTIONS_BOT_PAT` | ✅ |
| `OWNER_PR_PAT` | ✅ |
| `CODEX_AUTH_JSON` | ✅ |
| `WORKFLOWS_APP_ID` | ⬜ |
| `WORKFLOWS_APP_PRIVATE_KEY` | ⬜ |

### Variables

| Variable | Status |
|----------|--------|
| `ALLOWED_KEEPALIVE_LOGINS` | ⬜ |

---

## Execution Order

1. **Phase 0**: Archive existing workflows
2. **Phase 1**: Create labels (can be done in parallel with Phase 0)
3. **Phase 2**: Configure secrets/variables (verify App credentials)
4. **Phase 3**: Install consumer workflows (with fixes)
5. **Phase 4**: Install scripts and prompts
6. **Phase 5**: Verify and test

**Estimated time**: 1-2 hours for careful execution with verification at each phase.

---

*Document created from stranske/Workflows INTEGRATION_GUIDE.md and SETUP_CHECKLIST.md*
