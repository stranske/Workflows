# Consumer Repository Setup Checklist

This checklist guides you through setting up a new repository using the Workflows
template system. Follow each step carefully—**keepalive automation requires precise
configuration** and will fail silently if any element is missing.

> **Important**: It took approximately 25 PRs in the Travel-Plan-Permission repo
> before keepalive started functioning correctly. The lessons learned are encoded
> in this checklist.

> **See also**: [Consumer Repo Maintenance Guide](../ops/CONSUMER_REPO_MAINTENANCE.md)
> for debugging issues across multiple repos.

---

## Prerequisites

Before starting, ensure you have:

- [ ] Access to [stranske/Workflows](https://github.com/stranske/Workflows) repository
- [ ] A GitHub PAT for the service bot account (for SERVICE_BOT_PAT)
- [ ] Admin access to create repository secrets and variables
- [ ] Python 3.11+ installed locally for testing

---

## Phase 1: Repository Creation

### 1.1 Create Repository from Template

> **For existing repos**: Skip to [Phase 1.3](#13-existing-repository-setup) if 
> you're adding workflow system to an existing repository.

- [ ] Go to [stranske/Template](https://github.com/stranske/Template)
- [ ] Click **Use this template** → **Create a new repository**
- [ ] Choose owner: `stranske` (or your organization)
- [ ] Enter repository name
- [ ] Select **Private** or **Public** as appropriate
- [ ] Click **Create repository**

### 1.2 Clone and Verify Structure

```bash
git clone https://github.com/stranske/<your-repo>.git
cd <your-repo>
```

Verify these directories exist:
- [ ] `.github/workflows/` (should contain workflow files)
- [ ] `.github/scripts/` (should contain JS and Python scripts)
- [ ] `.github/templates/` (should contain `keepalive-instruction.md`)

### 1.3 Existing Repository Setup

For repositories that already exist (not created from Template):

1. Copy workflow files from `stranske/Workflows/templates/consumer-repo/.github/`:
   - [ ] `workflows/agents-*.yml` (all agent workflows)
   - [ ] `workflows/autofix.yml`
   - [ ] `workflows/pr-00-gate.yml` (or create custom - see below)
   - [ ] `codex/AGENT_INSTRUCTIONS.md`
   - [ ] `codex/prompts/keepalive_next_task.md`
   - [ ] `ISSUE_TEMPLATE/agent_task.yml`
   - [ ] `ISSUE_TEMPLATE/config.yml`
   - [ ] `PULL_REQUEST_TEMPLATE.md`

2. Copy documentation from `stranske/Workflows/templates/consumer-repo/docs/`:
   - [ ] `docs/AGENT_ISSUE_FORMAT.md` — How to format issues for agents
   - [ ] `docs/CI_SYSTEM_GUIDE.md` — CI system overview and troubleshooting
   - [ ] `docs/LABELS.md` — Label reference for workflow triggers

3. Update `.gitignore` to include codex working files:
   ```
   # Codex working files (preserved via workflow artifacts, not git)
   # CRITICAL: These must be gitignored to prevent merge conflicts when
   # multiple PRs run keepalive simultaneously. Each run rebuilds these files.
   codex-prompt.md
   codex-output.md
   verifier-context.md
   ```
   
   > **Why this matters**: When multiple PRs run keepalive at the same time,
   > each generates these files. If committed, merging one PR causes conflicts
   > in others. Historical data is preserved in PR comments and workflow artifacts.

4. **Gate workflow setup** — The Gate is critical for keepalive automation.
   
   **Option A: Use template Gate (standard Python projects)**
   
   If your repo uses pyproject.toml + ruff + pytest:
   - Copy `workflows/pr-00-gate.yml` directly from the template
   - The template calls `reusable-10-ci-python.yml` for standard Python CI
   
   **Option B: Create custom Gate (other project types)**
   
   If your repo has different CI needs, use the template as a **starting point**:
   
   ```bash
   # Start with the template
   cp templates/consumer-repo/.github/workflows/pr-00-gate.yml .github/workflows/
   ```
   
   Then customize the `test` job for your project while keeping:
   - The `summary` job structure (aggregates results)
   - The `Gate / gate` commit status (keepalive depends on this!)
   - The workflow name `Gate` and job name pattern
   
   **Required elements for custom Gate:**
   - [ ] Workflow named `Gate`
   - [ ] Summary job that posts `Gate / gate` commit status
   - [ ] Status must be `success`/`failure`/`error` (not `pending`)
   
   **Examples of custom Gates:**
   - `stranske/trip-planner` — Flask app with requirements.txt + pytest
   - `stranske/Manager-Database` — FastAPI with docker-compose + coverage

---

## Phase 2: Labels Configuration

> **Critical**: Workflows rely on specific labels to trigger automation. Missing labels
> cause silent failures.

### 2.1 Required Labels

Create these labels in **Settings** → **Labels** (exact names required):

| Label | Color | Description | Required For |
|-------|-------|-------------|--------------|
| `agent:codex` | `#0052CC` | Assigns Codex agent to issue | Issue intake, keepalive |
| `agent:needs-attention` | `#D93F0B` | Agent needs human help | Error recovery |
| `agents:keepalive` | `#0E8A16` | Enables keepalive automation | PR keepalive loops |
| `autofix` | `#1D76DB` | Triggers autofix on PR | Autofix workflow |
| `autofix:clean` | `#5319E7` | Aggressive autofix mode | Autofix workflow |
| `autofix:applied` | `#0E8A16` | Autofix was applied | Auto-created by workflow |
| `autofix:clean-only` | `#FBCA04` | Clean-only autofix | Autofix workflow |

Create each label:
- [ ] `agent:codex`
- [ ] `agent:needs-attention`
- [ ] `agents:keepalive`
- [ ] `autofix`
- [ ] `autofix:clean`
- [ ] `autofix:applied`
- [ ] `autofix:clean-only`

**Quick creation script:**
```bash
REPO="stranske/<your-repo>"

# Create required labels
gh label create "agent:codex" --color "0052CC" --description "Assigns Codex agent" --repo "$REPO" 2>/dev/null || echo "agent:codex exists"
gh label create "agent:needs-attention" --color "D93F0B" --description "Agent needs human help" --repo "$REPO" 2>/dev/null || echo "agent:needs-attention exists"
gh label create "agents:keepalive" --color "0E8A16" --description "Enables keepalive automation" --repo "$REPO" 2>/dev/null || echo "agents:keepalive exists"
gh label create "autofix" --color "1D76DB" --description "Triggers autofix on PR" --repo "$REPO" 2>/dev/null || echo "autofix exists"
gh label create "autofix:clean" --color "5319E7" --description "Aggressive autofix mode" --repo "$REPO" 2>/dev/null || echo "autofix:clean exists"
gh label create "autofix:applied" --color "0E8A16" --description "Autofix was applied" --repo "$REPO" 2>/dev/null || echo "autofix:applied exists"
gh label create "autofix:clean-only" --color "FBCA04" --description "Clean-only autofix" --repo "$REPO" 2>/dev/null || echo "autofix:clean-only exists"
```

### 2.2 Optional Labels

| Label | Color | Description | Use Case |
|-------|-------|-------------|----------|
| `agent:codex-invite` | `#0052CC` | Invites Codex to participate | Staged agent activation |
| `status:ready` | `#0E8A16` | Issue ready for processing | Manual workflow triggers |
| `agent:copilot` | `#0052CC` | Assigns Copilot agent | Alternative agent |

---

## Phase 3: Secrets and Access Configuration

> **Critical**: Keepalive automation will fail silently without these secrets.

### 3.1 Bot Collaborator Access

The service bot account needs **push access** to the repository for:
- Autofix commits
- Agent-created branches

```bash
# Add bot as collaborator with push access
curl -s -X PUT \
  -H "Authorization: token $YOUR_PAT" \
  "https://api.github.com/repos/stranske/<your-repo>/collaborators/stranske-automation-bot" \
  -d '{"permission": "push"}'
```

- [ ] Bot invitation sent
- [ ] Bot accepted invitation (check bot's GitHub notifications)

### 3.2 Required Secrets

Navigate to: **Settings** → **Secrets and variables** → **Actions** → **Secrets**

| Secret Name | Description | Source |
|-------------|-------------|--------|
| `SERVICE_BOT_PAT` | PAT for service bot account | Contact admin for token |
| `ACTIONS_BOT_PAT` | PAT for workflow dispatch | Same as SERVICE_BOT_PAT or dedicated |
| `OWNER_PR_PAT` | PAT for PR creation | Repository owner's PAT |
| `CODEX_AUTH_JSON` | Codex CLI authentication | Export from `~/.codex/auth.json` |

Add each secret:
- [ ] `SERVICE_BOT_PAT` — Required for orchestrator and agent workflows
- [ ] `ACTIONS_BOT_PAT` — Required for triggering workflows between repos
- [ ] `OWNER_PR_PAT` — Required for creating PRs from agent bridge
- [ ] `CODEX_AUTH_JSON` — Required for Codex CLI to authenticate with ChatGPT

### 3.3 Required Variables

Navigate to: **Settings** → **Secrets and variables** → **Actions** → **Variables**

| Variable Name | Description | Example Value |
|---------------|-------------|---------------|
| `ALLOWED_KEEPALIVE_LOGINS` | GitHub usernames allowed to trigger keepalive | `stranske` |

Add the variable:
- [ ] `ALLOWED_KEEPALIVE_LOGINS` — Comma-separated list of usernames

---

## Phase 4: Workflow Configuration

### 4.1 Verify Workflow Files

Check that these workflows exist in `.github/workflows/`:

| Workflow | Purpose | Critical for Keepalive |
|----------|---------|------------------------|
| `pr-00-gate.yml` | CI enforcement, posts commit status | **YES** |
| `agents-pr-meta.yml` | Detects keepalive comments | **YES** |
| `agents-70-orchestrator.yml` | Runs keepalive sweeps (every 30 min) | **YES** |
| `agents-63-issue-intake.yml` | Creates PRs from labeled issues (full workflow) | No |
| `agents-keepalive-loop.yml` | Keepalive iteration execution | **YES** |
| `agents-verifier.yml` | Post-merge verification | No |
| `autofix.yml` | Auto-fixes lint/format issues | No |
| `ci.yml` | Thin caller for Python CI | No |
| `maint-sync-workflows.yml` | Local sync check (weekly) | Recommended |

- [ ] All workflow files present
- [ ] Workflow files reference `stranske/Workflows@main`


### 4.1b Validate Workflow File Naming

> **Critical**: Consumer repos must use the correct workflow file naming convention.
> Old naming (without numbers) indicates incomplete migration.

**Expected files** (correct naming):
- `agents-63-issue-intake.yml` — Full workflow with ChatGPT sync (NOT the old thin caller)
- `agents-70-orchestrator.yml` — Orchestrator with numbered naming

**Deprecated or legacy files:**
- ~~`agents-issue-intake.yml`~~ — Old thin caller, replaced by `agents-63-issue-intake.yml`
- `agents-orchestrator.yml` — Legacy unnumbered naming; still valid and may coexist, but prefer `agents-70-orchestrator.yml`

> **Why both orchestrator files may exist**: The `maint-68-sync-consumer-repos` workflow
> uses a mapping syntax (`"agents-70-orchestrator.yml:agents-orchestrator.yml"`) that
> syncs the source file to both names. This ensures repos using either convention
> receive updates. New repos should use `agents-70-orchestrator.yml`; existing repos
> with `agents-orchestrator.yml` continue to work.

**Validation checklist:**
- [ ] No deprecated workflow files present
- [ ] `agents-63-issue-intake.yml` exists (NOT `agents-issue-intake.yml`)
- [ ] `agents-70-orchestrator.yml` exists (may coexist with `agents-orchestrator.yml`)
- [ ] `maint-sync-workflows.yml` exists for local sync checks

**To fix if using old naming:**
```bash
# Remove old thin caller workflow
rm .github/workflows/agents-issue-intake.yml

# Copy full workflow from Workflows repo
curl -o .github/workflows/agents-63-issue-intake.yml \
  https://raw.githubusercontent.com/stranske/Workflows/main/.github/workflows/agents-63-issue-intake.yml

# Copy orchestrator with numbered naming  
curl -o .github/workflows/agents-70-orchestrator.yml \
  https://raw.githubusercontent.com/stranske/Workflows/main/templates/consumer-repo/.github/workflows/agents-orchestrator.yml

# Copy local sync check workflow
curl -o .github/workflows/maint-sync-workflows.yml \
  https://raw.githubusercontent.com/stranske/Travel-Plan-Permission/main/.github/workflows/maint-sync-workflows.yml
```

> **Lesson learned**: When writing workflow sync scripts that use `curl` to download
> files, always verify both success AND that the file exists with content:
> ```bash
> # BAD - curl failure silently continues
> curl -sfL "$URL" -o "$FILE" 2>/dev/null || continue
> 
> # GOOD - explicit failure tracking and file verification
> download_failed=false
> if ! curl -sfL "$URL" -o "$FILE" 2>/dev/null; then
>   download_failed=true
> fi
> if [ "$download_failed" = "true" ] || [ ! -s "$FILE" ]; then
>   echo "Download failed: $FILE"
>   continue
> fi
> ```
> This pattern was added to consumer repo `maint-sync-workflows.yml` files after
> silent failures masked sync issues.
> **⚠️ CRITICAL: Fix reusable workflow references after copying!**
> 
> The `agents-63-issue-intake.yml` file in the Workflows repo contains a LOCAL 
> reference to `reusable-agents-issue-bridge.yml`. This works in Workflows but
> **will break in consumer repos** because the file doesn't exist locally.
> 
> After copying, you MUST change line ~1171 from:
> ```yaml
> uses: ./.github/workflows/reusable-agents-issue-bridge.yml
> ```
> To the remote reference:
> ```yaml
> uses: stranske/Workflows/.github/workflows/reusable-agents-issue-bridge.yml@main
> ```
> 
> **Alternative**: Copy from Template repo instead (already has correct reference):
> ```bash
> curl -o .github/workflows/agents-63-issue-intake.yml \
>   https://raw.githubusercontent.com/stranske/Template/main/.github/workflows/agents-63-issue-intake.yml
> ```

### 4.2 Autofix Versions Configuration

> **Important**: Each repository maintains its own `autofix-versions.env` file
> with dependency versions matching its lock files. This file is NOT synced.

Create `.github/workflows/autofix-versions.env`:

```bash
# Tool versions for autofix - match your project's lock files
RUFF_VERSION=0.8.1
MYPY_VERSION=1.14.0
BLACK_VERSION=24.10.0
ISORT_VERSION=5.13.2
```

- [ ] `autofix-versions.env` file created
- [ ] Versions match project's dependency versions

To find your current versions:
```bash
# From your project's requirements or pyproject.toml
grep -E "ruff|mypy|black|isort" requirements*.txt pyproject.toml 2>/dev/null
```

### 4.3 Critical Workflow Configuration

**In `agents-pr-meta.yml`:**

The `pr_number` input MUST use `fromJSON()` to convert the string output to a number:

```yaml
# ❌ WRONG - will silently skip the job
pr_number: ${{ needs.resolve_pr.outputs.pr_number }}

# ✅ CORRECT - properly converts to number
pr_number: ${{ fromJSON(needs.resolve_pr.outputs.pr_number) }}
```

- [ ] Verify `fromJSON()` wrapper is present in all `pr_number` inputs

**In `pr-00-gate.yml`:**

The Gate workflow MUST post a commit status for keepalive to detect when CI passes:

```yaml
- name: Report Gate commit status
  uses: actions/github-script@v7
  with:
    script: |
      await github.rest.repos.createCommitStatus({
        owner, repo, sha,
        state,
        context: 'Gate / gate',  # This exact context is expected
        description,
        target_url: targetUrl,
      });
```

- [ ] Verify commit status step exists in Gate summary job

**In `agents-pr-meta.yml` (workflow_run trigger):**

The workflow MUST have a `workflow_run` trigger for Gate completion:

```yaml
on:
  # ... other triggers ...
  workflow_run:
    workflows: ["Gate"]
    types: [completed]
```

This handles the race condition where a human posts `@codex` before Gate finishes.

- [ ] Verify `workflow_run` trigger is present
- [ ] Verify `allow_replay: true` is passed to reusable workflow for Gate completion

---

## Phase 5: Scripts Configuration

### 5.1 Required JavaScript Scripts

These scripts MUST exist in `.github/scripts/`:

| Script | Purpose | Required By |
|--------|---------|-------------|
| `issue_pr_locator.js` | Finds PRs linked to issues | Agent bridge |
| `issue_context_utils.js` | Issue context helpers | Agent bridge |
| `issue_scope_parser.js` | Parses scope from issue body | Agent bridge |
| `keepalive_instruction_template.js` | Generates keepalive instructions | Agent bridge |

> **Source**: These scripts are copied from `stranske/Workflows/.github/scripts/`
> and are automatically synced by the `maint-68-sync-consumer-repos` workflow.
> 
> **Manual setup**: If setting up before sync, copy from the Workflows repo or
> use the consumer-repo template at `templates/consumer-repo/.github/scripts/`.

- [ ] All 4 JS scripts present

### 5.2 Required Python Scripts

These scripts MUST exist in `.github/scripts/`:

| Script | Purpose | Required By |
|--------|---------|-------------|
| `decode_raw_input.py` | Decodes ChatGPT input | agents-63 chatgpt_sync |
| `parse_chatgpt_topics.py` | Parses topics from input | agents-63 chatgpt_sync |
| `fallback_split.py` | Fallback topic splitting | agents-63 chatgpt_sync |

- [ ] All 3 Python scripts present

### 5.3 Required Codex Prompts

These files MUST exist in `.github/codex/` for the keepalive pipeline:

| File | Purpose |
|------|---------|
| `AGENT_INSTRUCTIONS.md` | Security boundaries and operational guidelines for Codex |
| `prompts/keepalive_next_task.md` | Prompt template for keepalive iterations |

- [ ] `.github/codex/AGENT_INSTRUCTIONS.md` present
- [ ] `.github/codex/prompts/keepalive_next_task.md` present

> **Critical**: Without these files, the `reusable-codex-run.yml` workflow will
> fail with "Base prompt file not found".

### 5.4 Required Templates

Templates MUST exist in `.github/templates/`:

| Template | Purpose |
|----------|---------|
| `keepalive-instruction.md` | Instructions for Codex in keepalive rounds |

- [ ] Template file present

---

## Phase 6: Project Files

### 6.1 Issues.txt Format

If using ChatGPT sync, create an `Issues.txt` file in the repository root:

```text
1) Issue title here
Labels: agent:codex, enhancement, area:backend

Why
Describe why this work is needed.

Scope
- What is included
- What is not included (Non-Goals)

Tasks
- [ ] First task to complete
- [ ] Second task to complete
- [ ] Third task to complete

Acceptance criteria
- First acceptance criterion
- Second acceptance criterion

Implementation notes
Any technical notes or guidance.

2) Second issue title
Labels: agent:codex, bug

Why
...
```

- [ ] `Issues.txt` created (if using ChatGPT sync)
- [ ] Each issue has `Labels:` line with `agent:codex`
- [ ] Each issue has Why, Scope, Tasks, and Acceptance criteria sections

### 6.2 Python Project Files

For Python projects, ensure:

- [ ] `pyproject.toml` exists with dependencies
- [ ] `src/` directory structure follows package conventions
- [ ] `tests/` directory exists with `conftest.py`
- [ ] `.python-version` file specifies Python version (e.g., `3.11`)

---

## Phase 7: Branch Protection (Optional but Recommended)

> **Note**: Configure branch protection AFTER your first successful PR to avoid
> blocking the initial setup.

### 7.1 Recommended Settings

Navigate to: **Settings** → **Branches** → **Add branch protection rule**

For the `main` branch:

- [ ] **Require a pull request before merging**
- [ ] **Require status checks to pass before merging**
  - [ ] Add required status check: `Gate / gate`
- [ ] **Require branches to be up to date before merging**
- [ ] **Do not allow bypassing the above settings** (optional, for strict enforcement)

---

## Phase 8: Functional Areas Walkthrough

This section explains each functional area of the workflow system, how to verify
it's properly configured, and how to test it.

### 8.1 Gate/CI System

**Purpose**: Enforces code quality by running tests, linting, and formatting checks
on every PR. Posts a commit status that other workflows depend on.

**Workflows involved**:
| Workflow | Role |
|----------|------|
| `pr-00-gate.yml` | Orchestrates CI jobs, posts `Gate / gate` commit status |
| `ci.yml` | Optional thin caller for Python CI (if not using Gate's built-in) |

**Key dependencies**:
- `autofix-versions.env` — Tool version pins for consistent behavior

**Verification checklist**:
- [ ] `pr-00-gate.yml` exists in `.github/workflows/`
- [ ] Workflow has a `summary` job that posts commit status
- [ ] Commit status context is exactly `Gate / gate`
- [ ] `autofix-versions.env` exists with tool versions

**How to test**:
1. Create a PR with a simple change
2. Verify the Gate workflow runs
3. Check that commit status `Gate / gate` appears on the PR
4. Status should be `success`, `failure`, or `error` (never stuck at `pending`)

**Troubleshooting**:
- If status stays `pending`: Check the summary job ran and used `createCommitStatus`
- If tests fail unexpectedly: Verify tool versions in `autofix-versions.env` match local

---

### 8.2 Keepalive System

**Purpose**: Automatically continues agent work through multiple iterations until
tasks are complete or the iteration limit is reached.

**Workflows involved**:
| Workflow | Role |
|----------|------|
| `agents-pr-meta.yml` | Detects `@codex` comments, triggers keepalive |
| `agents-orchestrator.yml` | Scheduled sweeps to find stalled PRs |
| `agents-keepalive-loop.yml` | Executes keepalive iterations |

**Key dependencies**:
- `.github/codex/AGENT_INSTRUCTIONS.md` — Agent security boundaries
- `.github/codex/prompts/keepalive_next_task.md` — Iteration prompt template
- `Gate / gate` commit status — Keepalive waits for CI before proceeding
- `ALLOWED_KEEPALIVE_LOGINS` variable — Who can trigger keepalive
- `.gitignore` entries for `codex-prompt.md`, `codex-output.md`, `verifier-context.md`

**Verification checklist**:
- [ ] `agents-pr-meta.yml` exists with `issue_comment` and `workflow_run` triggers
- [ ] `agents-orchestrator.yml` exists with `schedule` trigger
- [ ] `agents-keepalive-loop.yml` exists
- [ ] `.github/codex/AGENT_INSTRUCTIONS.md` exists
- [ ] `.github/codex/prompts/keepalive_next_task.md` exists
- [ ] `ALLOWED_KEEPALIVE_LOGINS` variable is set in repo settings
- [ ] `.gitignore` includes codex working files (prevents multi-PR conflicts)

**How to test**:
1. Create a PR from an issue with `agent:codex` label
2. Post `@codex` comment on the PR
3. Verify `agents-pr-meta.yml` workflow triggers
4. Check workflow logs for keepalive evaluation
5. If Gate passed, keepalive should dispatch to `agents-keepalive-loop.yml`

**Troubleshooting**:
- `pr_meta_comment` job skipped: Check `pr_number` uses `fromJSON()` wrapper
- "keepalive disabled": Check `ALLOWED_KEEPALIVE_LOGINS` includes comment author
- "gate-not-concluded": Gate hasn't finished; wait or check Gate workflow
- Missing codex files: Add from `templates/consumer-repo/.github/codex/`

---

### 8.3 Autofix System

**Purpose**: Automatically fixes code style issues (formatting, linting, imports)
when the `autofix` or `autofix:clean` label is added to a PR.

**Workflows involved**:
| Workflow | Role |
|----------|------|
| `autofix.yml` | Thin caller that triggers on label, delegates to reusable workflow |

**Key dependencies**:
- `autofix-versions.env` — Tool versions (ruff, black, mypy, etc.)
- `SERVICE_BOT_PAT` secret — For pushing autofix commits
- `autofix` label — Triggers standard autofix
- `autofix:clean` label — Triggers aggressive clean mode

**Verification checklist**:
- [ ] `autofix.yml` exists in `.github/workflows/`
- [ ] `autofix-versions.env` exists with tool versions
- [ ] `SERVICE_BOT_PAT` secret is configured
- [ ] Labels `autofix` and `autofix:clean` exist in repository

**How to test**:
1. Create a PR with intentional style issues (wrong indentation, unsorted imports)
2. Add the `autofix` label to the PR
3. Verify autofix workflow runs
4. Check that autofix commits are pushed to the PR branch
5. Verify `autofix:applied` label is added after successful fix

**Troubleshooting**:
- Autofix doesn't run: Check label name is exactly `autofix` (case-sensitive)
- Fixes don't match local: Ensure `autofix-versions.env` matches local tool versions
- Permission denied on push: Check `SERVICE_BOT_PAT` has push access

---

### 8.4 Issue Intake System

**Purpose**: Automatically creates PRs from issues labeled with `agent:codex`,
bootstrapping agent work with a linked branch and draft PR.

**Workflows involved**:
| Workflow | Role |
|----------|------|
| `agents-issue-intake.yml` | Triggers on issue label, creates branch and PR |

**Key dependencies**:
- `agent:codex` label — Triggers intake
- `SERVICE_BOT_PAT` secret — For creating branches
- `OWNER_PR_PAT` secret — For creating PRs
- `.github/scripts/` — JavaScript scripts required by reusable workflow

**Verification checklist**:
- [ ] `agents-issue-intake.yml` exists in `.github/workflows/`
- [ ] `agent:codex` label exists in repository
- [ ] `SERVICE_BOT_PAT` secret is configured
- [ ] `OWNER_PR_PAT` secret is configured
- [ ] Issue templates exist in `.github/ISSUE_TEMPLATE/`
- [ ] JavaScript scripts exist in `.github/scripts/` (see Phase 5.1)

**How to test**:
1. Create an issue with clear Tasks and Acceptance Criteria sections
2. Add the `agent:codex` label
3. Verify intake workflow runs
4. Check that a branch `codex/issue-<number>` is created
5. Verify a draft PR is opened linking to the issue

**Troubleshooting**:
- Intake doesn't trigger: Check label is `agent:codex` (not `codex` or `agent-codex`)
- PR not created: Check `OWNER_PR_PAT` has repo and workflow permissions
- Branch not created: Check `SERVICE_BOT_PAT` has push access
- `MODULE_NOT_FOUND` error: Missing `.github/scripts/*.js` files — copy from 
  `stranske/Workflows/.github/scripts/` or run the sync workflow

---

### 8.5 Verifier System

**Purpose**: After a PR is merged, verifies that acceptance criteria were met and
creates follow-up issues for any unmet criteria.

**Workflows involved**:
| Workflow | Role |
|----------|------|
| `agents-verifier.yml` | Triggers on PR merge, evaluates acceptance criteria |

**Key dependencies**:
- PR must have Tasks AND Acceptance Criteria sections (or linked issue does)
- CI results are collected for context

**Verification checklist**:
- [ ] `agents-verifier.yml` exists in `.github/workflows/`
- [ ] Workflow has `pull_request` trigger with `closed` type

**How to test**:
1. Create a PR with Tasks and Acceptance Criteria sections
2. Merge the PR
3. Verify verifier workflow runs
4. Check workflow output for verification results
5. If criteria unmet, verify follow-up issue is created

**Troubleshooting**:
- Verifier skipped: PR or linked issue must have BOTH Tasks and Acceptance Criteria
- No follow-up issue: All criteria were met (success case)
- Wrong criteria evaluated: Check linked issues are properly referenced

---

### 8.6 Orchestrator System

**Purpose**: Runs scheduled sweeps to find PRs that need keepalive attention,
including watchdog checks for stalled automation.

**Workflows involved**:
| Workflow | Role |
|----------|------|
| `agents-orchestrator.yml` | Scheduled (every 30 min) keepalive sweeps |

**Key dependencies**:
- Scheduled cron trigger
- `SERVICE_BOT_PAT` for cross-repo operations

**Verification checklist**:
- [ ] `agents-orchestrator.yml` exists in `.github/workflows/`
- [ ] Workflow has `schedule` trigger with cron expression
- [ ] `SERVICE_BOT_PAT` secret is configured

**How to test**:
1. Manually dispatch the orchestrator workflow
2. Check workflow logs for PR sweep results
3. Verify it identifies PRs needing keepalive

**Troubleshooting**:
- Scheduled runs don't occur: GitHub may delay/skip schedules on inactive repos
- No PRs found: Check filter criteria (open PRs with agent labels)

---

### 8.7 System Dependencies Diagram

```
┌─────────────────┐
│   Issue Intake  │  Creates branch + PR from labeled issue
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│      Gate       │  Runs CI, posts commit status
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   PR Meta       │  Detects @codex, checks Gate status
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Keepalive Loop  │  Runs agent iterations
└────────┬────────┘
         │
         ├──────────────────────┐
         ▼                      ▼
┌─────────────────┐    ┌─────────────────┐
│    Autofix      │    │  Orchestrator   │
│  (on demand)    │    │  (scheduled)    │
└─────────────────┘    └─────────────────┘
         │
         ▼
┌─────────────────┐
│    Verifier     │  Post-merge validation
└─────────────────┘
```

---

## Phase 9: Testing the Setup

### 9.1 Test CI Workflow

1. Create a test branch:
   ```bash
   git checkout -b test/ci-setup
   echo "# Test" >> README.md
   git add README.md
   git commit -m "test: verify CI setup"
   git push -u origin test/ci-setup
   ```

2. Open a PR and verify:
   - [ ] Gate workflow triggers
   - [ ] Python CI job runs (if Python code exists)
   - [ ] Commit status is posted (`Gate / gate`)

### 9.2 Test Keepalive (After Gate Works)

1. Create an issue with `agent:codex` label
2. Wait for agents-63 to create a bootstrap PR
3. Post `@codex` comment on the PR
4. Verify:
   - [ ] agents-pr-meta workflow triggers
   - [ ] Keepalive detection runs
   - [ ] agents:keepalive label is added (if conditions met)

---

## Troubleshooting

### Keepalive Not Working

| Symptom | Cause | Fix |
|---------|-------|-----|
| `pr_meta_comment` job skipped | `pr_number` type mismatch | Use `fromJSON()` wrapper |
| "Module not found" errors | Missing JS scripts | Add scripts from template |
| Gate completes but no keepalive | Missing `workflow_run` trigger | Add trigger for Gate |
| Keepalive defers with `gate-not-concluded` | Gate still running | Wait for Gate, or check `allow_replay` |

### Debug Logging

Enable debug mode in workflow dispatch:
```yaml
inputs:
  debug:
    description: 'Enable debug logging'
    type: boolean
    default: false
```

### Common Mistakes

1. **Forgetting `fromJSON()`** — Job outputs are always strings; reusable workflows expecting numbers will silently skip
2. **Missing commit status** — Keepalive checks for `Gate / gate` status to know when CI passes
3. **Wrong workflow name in trigger** — The `workflows:` array must match the exact workflow `name:` field
4. **Missing scripts** — Scripts are NOT automatically synced; they must exist in consumer repo
5. **Silent download failures** — `curl -sf` failing without verification leaves empty/missing files
6. **Codex-specific naming in job names** — Prefer agent-agnostic names (e.g., "Validate agent issue labels" not "Validate Codex issue labels") for flexibility

> **Note on naming conventions**: The workflow source files in stranske/Workflows
> contain some Codex-specific references (job names, descriptions, variable names).
> While variable names like `post_codex_input` are preserved for backward compatibility,
> user-facing job names should use agent-agnostic terminology. Copilot code review
> may flag these as suggestions.

---

## Quick Reference

### Minimum Files for Keepalive

```
.github/
├── codex/
│   ├── AGENT_INSTRUCTIONS.md
│   └── prompts/
│       └── keepalive_next_task.md
├── scripts/
│   ├── decode_raw_input.py
│   ├── fallback_split.py
│   ├── issue_context_utils.js
│   ├── issue_pr_locator.js
│   ├── issue_scope_parser.js
│   ├── keepalive_instruction_template.js
│   └── parse_chatgpt_topics.py
├── templates/
│   └── keepalive-instruction.md
└── workflows/
    ├── agents-63-issue-intake.yml
    ├── agents-70-orchestrator.yml
    ├── agents-pr-meta.yml
    ├── autofix.yml
    ├── ci.yml
    └── pr-00-gate.yml
```

### Required Secrets

- `SERVICE_BOT_PAT`
- `ACTIONS_BOT_PAT`
- `OWNER_PR_PAT`
- `CODEX_AUTH_JSON`

### Required Variables

- `ALLOWED_KEEPALIVE_LOGINS`

---

## Phase 10: Register for Automatic Sync (Optional)

To receive automatic updates when workflow templates change:

1. Add your repo to `REGISTERED_CONSUMER_REPOS` in 
   `stranske/Workflows/.github/workflows/maint-68-sync-consumer-repos.yml`

2. Verify sync works:
   ```bash
   gh workflow run "Maint 68 Sync Consumer Repos" \
     --repo stranske/Workflows \
     -f repos="stranske/<your-repo>" \
     -f dry_run=true
   ```

**Note**: Repos with custom Gate workflows should still be registered—only
the thin caller workflows are synced, not custom implementations.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.1 | 2025-12-27 | Added existing repo setup, bot collaborator access, sync registration |
| 1.0 | 2025-01 | Initial checklist based on Travel-Plan-Permission learnings |
