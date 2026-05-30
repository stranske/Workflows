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
- [ ] Claude Code login/session available if you want Claude-run workflows
- [ ] Python 3.12+ installed locally for testing
- [ ] GitHub CLI (`gh`) installed + authenticated (`brew install gh`; `gh auth status`) — the repo/label/secret steps below use it
- [ ] Access to the team credentials store (e.g. `Code/Numbers/values.txt`), labeled by secret name — source for the Phase 3 secrets the table marks "contact admin"

---

## Phase 1: Repository Creation

### 1.1 Create Repository from Template

> **For existing repos**: Skip to [Phase 1.3](#13-existing-repository-setup) if 
> you're adding workflow system to an existing repository.

- [ ] Create the consumer repo from your chosen template source:
  - [ ] Preferred: start from the consumer repo template under `stranske/Workflows/templates/consumer-repo/` (copied into a new repo)
  - [ ] Alternative: use a dedicated template repo (for example [stranske/Template](https://github.com/stranske/Template)) if your org maintains one
- [ ] Create via GitHub CLI (the UI "Use this template" path still works too):
  ```bash
  gh repo create stranske/<your-repo> --public --template stranske/Template \
    --description "<short description>"
  ```
  Use `--private` if appropriate. `stranske/Template` is a GitHub *template* repo, so `--template` copies its full scaffold in one step.

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
   - [ ] ~~`PULL_REQUEST_TEMPLATE.md`~~ **SKIP THIS** — See note below

   > **Important**: Do NOT copy `PULL_REQUEST_TEMPLATE.md` if it exists in the template.
   > The generic PR template adds boilerplate text to every PR, which is unhelpful for
   > agent-created PRs and clutters the PR description. Delete this file if it was
   > already copied from the template:
   > ```bash
   > git rm .github/PULL_REQUEST_TEMPLATE.md
   > git commit -m "chore: remove generic PR template"
   > ```

2. Copy documentation from `stranske/Workflows/templates/consumer-repo/docs/`:
   - [ ] `docs/AGENT_ISSUE_FORMAT.md` — How to format issues for agents
   - [ ] `docs/CI_SYSTEM_GUIDE.md` — CI system overview and troubleshooting
   - [ ] `docs/LABELS.md` — Label reference for workflow triggers

3. Update `.gitignore` to include codex working files:
   ```
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
   
   > **Why this matters**: When multiple PRs run keepalive at the same time,
   > each generates these files. If committed, merging one PR causes conflicts
   > in others. Historical data is preserved in PR comments and workflow artifacts.
   > 
   > The workflow now generates PR-specific filenames (e.g., `codex-output-123.md`)
   > and explicitly excludes them from commits, but the `.gitignore` provides
   > defense-in-depth.

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
| `agent:retry` | `#D93F0B` | Retries keepalive loop for agent PRs | Keepalive recovery |
| `agent:needs-attention` | `#D93F0B` | Agent needs human help | Error recovery |
| `agents:keepalive` | `#0E8A16` | Enables keepalive automation | PR keepalive loops |
| `agents:auto-pilot` | `#0052CC` | Triggers end-to-end auto-pilot pipeline | Issue automation |
| `runner:<agent>` | `#6f42c1` | Optional auto-pilot override (`runner:claude`, etc.) without triggering the issue intake workflow | Issue automation |
| `agents:decompose` | `#5319E7` | Triggers issue decomposition workflow | Issue planning |
| `agents:format` | `#5319E7` | Triggers direct issue formatting | Issue formatting |
| `agents:optimize` | `#5319E7` | Triggers issue analysis/suggestions | Issue optimization |
| `agents:apply-suggestions` | `#5319E7` | Applies optimizer suggestions | Issue optimization |
| `autofix` | `#1D76DB` | Triggers autofix on PR | Autofix workflow |
| `autofix:clean` | `#5319E7` | Aggressive autofix mode | Autofix workflow |
| `autofix:bot-comments` | `#1D76DB` | Triggers bot comment autofix sweep | PR bot-comment cleanup |
| `autofix:applied` | `#0E8A16` | Autofix was applied | Auto-created by workflow |
| `autofix:clean-only` | `#FBCA04` | Clean-only autofix | Autofix workflow |
| `verify:create-issue` | `#5319E7` | Creates follow-up issue from verifier output | Verify follow-up |
| `verify:create-new-pr` | `#5319E7` | Creates follow-up PR from verifier output | Verify follow-up |

Create each label:
- [ ] `agent:codex`
- [ ] `agent:retry`
- [ ] `agent:needs-attention`
- [ ] `agents:keepalive`
- [ ] `agents:auto-pilot`
- [ ] `runner:codex` (optional override, repeat per agent)
- [ ] `agents:decompose`
- [ ] `agents:format`
- [ ] `agents:optimize`
- [ ] `agents:apply-suggestions`
- [ ] `autofix`
- [ ] `autofix:clean`
- [ ] `autofix:bot-comments`
- [ ] `autofix:applied`
- [ ] `autofix:clean-only`
- [ ] `verify:create-issue`
- [ ] `verify:create-new-pr`

**Quick creation script:**
```bash
REPO="stranske/<your-repo>"

# Create required labels
gh label create "agent:codex" --color "0052CC" --description "Assigns Codex agent" --repo "$REPO" 2>/dev/null || echo "agent:codex exists"
gh label create "agent:retry" --color "D93F0B" --description "Retries keepalive loop" --repo "$REPO" 2>/dev/null || echo "agent:retry exists"
gh label create "agent:needs-attention" --color "D93F0B" --description "Agent needs human help" --repo "$REPO" 2>/dev/null || echo "agent:needs-attention exists"
gh label create "agents:keepalive" --color "0E8A16" --description "Enables keepalive automation" --repo "$REPO" 2>/dev/null || echo "agents:keepalive exists"
gh label create "agents:auto-pilot" --color "0052CC" --description "Runs full auto-pilot issue pipeline" --repo "$REPO" 2>/dev/null || echo "agents:auto-pilot exists"
gh label create "runner:codex" --color "6f42c1" --description "Auto-pilot runner override: codex" --repo "$REPO" 2>/dev/null || echo "runner:codex exists"
gh label create "agents:decompose" --color "5319E7" --description "Triggers issue decomposition workflow" --repo "$REPO" 2>/dev/null || echo "agents:decompose exists"
gh label create "agents:format" --color "5319E7" --description "Formats issue into template" --repo "$REPO" 2>/dev/null || echo "agents:format exists"
gh label create "agents:optimize" --color "5319E7" --description "Analyzes issue and posts suggestions" --repo "$REPO" 2>/dev/null || echo "agents:optimize exists"
gh label create "agents:apply-suggestions" --color "5319E7" --description "Applies optimizer suggestions" --repo "$REPO" 2>/dev/null || echo "agents:apply-suggestions exists"
gh label create "autofix" --color "1D76DB" --description "Triggers autofix on PR" --repo "$REPO" 2>/dev/null || echo "autofix exists"
gh label create "autofix:clean" --color "5319E7" --description "Aggressive autofix mode" --repo "$REPO" 2>/dev/null || echo "autofix:clean exists"
gh label create "autofix:bot-comments" --color "1D76DB" --description "Triggers bot comment autofix sweep" --repo "$REPO" 2>/dev/null || echo "autofix:bot-comments exists"
gh label create "autofix:applied" --color "0E8A16" --description "Autofix was applied" --repo "$REPO" 2>/dev/null || echo "autofix:applied exists"
gh label create "autofix:clean-only" --color "FBCA04" --description "Clean-only autofix" --repo "$REPO" 2>/dev/null || echo "autofix:clean-only exists"
gh label create "verify:create-issue" --color "5319E7" --description "Creates follow-up issue from verifier output" --repo "$REPO" 2>/dev/null || echo "verify:create-issue exists"
gh label create "verify:create-new-pr" --color "5319E7" --description "Creates follow-up PR from verifier output" --repo "$REPO" 2>/dev/null || echo "verify:create-new-pr exists"
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

> **Automation shortcut**: The GitHub settings toggles in sections 3.1, 3.3, and 3.3.1
> (bot collaborator, `USE_CONSOLIDATED_WORKFLOWS` / `ALLOWED_KEEPALIVE_LOGINS`
> variables, and `default_workflow_permissions=write`) can be applied in one shot
> from the canonical Workflows repo by running the **Maint 83 Bootstrap Consumer**
> workflow (`scripts/bootstrap_consumer_settings.py`) against this repo. Secrets in
> section 3.2 still require manual setup. The collaborator invite still has to be
> accepted by the bot account.

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
| `AGENTS_AUTOMATION_PAT` | PAT used by autofix/retry flows when available | Contact admin for token |
| `OWNER_PR_PAT` | PAT for PR creation | Repository owner's PAT |
| `CODEX_AUTH_JSON` | Codex CLI authentication | Export from `~/.codex/auth.json` |
| `WORKFLOWS_APP_CLIENT_ID` | GitHub App client ID for preferred token minting | Contact admin for App client ID |
| `WORKFLOWS_APP_ID` | GitHub App ID for token minting | Contact admin for App ID |
| `WORKFLOWS_APP_PRIVATE_KEY` | GitHub App private key | Contact admin for private key |
| `GH_APP_CLIENT_ID` | Bot-comment GitHub App client ID | Contact admin for App client ID |
| `GH_APP_ID` | Bot-comment legacy GitHub App ID fallback | Contact admin for App ID |
| `GH_APP_PRIVATE_KEY` | Bot-comment GitHub App private key | Contact admin for private key |
| `KEEPALIVE_APP_ID` | Keepalive App ID (preferred for keepalive loop auth) | Contact admin for App ID |
| `KEEPALIVE_APP_PRIVATE_KEY` | Keepalive App private key | Contact admin for private key |
| `OPENAI_API_KEY` | OpenAI API key for verify/optimizer/decompose flows | Contact admin for token |
| `CLAUDE_API_STRANSKE` | Claude API key for verify/optimizer/decompose flows | Contact admin for token |
| `CLAUDE_CODE_OAUTH_TOKEN` | Claude Code OAuth token (preferred for Claude CLI runs) | `claude setup-token` |
| `CLAUDE_AUTH_JSON` | Claude auth JSON fallback when OAuth token is unavailable | Export from existing Claude auth file |

Add each secret:
- [ ] `SERVICE_BOT_PAT` — Required for orchestrator and agent workflows
- [ ] `ACTIONS_BOT_PAT` — Required for triggering workflows between repos
- [ ] `AGENTS_AUTOMATION_PAT` — Recommended for autofix/retry dispatches
- [ ] `OWNER_PR_PAT` — Required for creating PRs from agent bridge
- [ ] `CODEX_AUTH_JSON` — Required for Codex CLI to authenticate with ChatGPT
- [ ] `WORKFLOWS_APP_CLIENT_ID` — Preferred GitHub App token minting path
- [ ] `WORKFLOWS_APP_ID` — **Required for keepalive** - Used for GitHub App token minting
- [ ] `WORKFLOWS_APP_PRIVATE_KEY` — **Required for keepalive** - GitHub App authentication
- [ ] `GH_APP_CLIENT_ID` — Preferred bot-comment App auth path
- [ ] `GH_APP_ID` — Legacy bot-comment App ID fallback
- [ ] `GH_APP_PRIVATE_KEY` — Bot-comment App private key
- [ ] `KEEPALIVE_APP_ID` — **Required for keepalive parity** - Explicit keepalive app alias
- [ ] `KEEPALIVE_APP_PRIVATE_KEY` — **Required for keepalive parity** - Explicit keepalive app key
- [ ] `OPENAI_API_KEY` — Required for verify/decompose/optimizer workflows
- [ ] `CLAUDE_API_STRANSKE` — Required for verify/decompose/optimizer workflows
- [ ] `CLAUDE_CODE_OAUTH_TOKEN` (or `CLAUDE_AUTH_JSON`) — Required for Claude CLI workflow runs

### 3.2.1 Bulk PAT Sync (No Organization Required)

If you manage multiple repositories without GitHub organization secrets, use the
shared script to fan out PATs from one local source of truth:

```bash
# 1) Export PAT values once in your local shell
export SERVICE_BOT_PAT='...'
export ACTIONS_BOT_PAT='...'
export OWNER_PR_PAT='...'
export AGENTS_AUTOMATION_PAT='...'

# 2) Sync to all repos in one command
scripts/sync_pat_secrets.sh \
  --repos stranske/Counter_Risk,stranske/Template,stranske/Manager-Database \
  --verify
```

Notes:
- `--verify` validates each token against GitHub API before writing secrets.
- This avoids per-repo copy/paste while keeping repository-level secrets.
- Script path: `scripts/sync_pat_secrets.sh`.

### 3.2.2 Codex CLI Secret (`CODEX_AUTH_JSON`) — Explicit Setup

`CODEX_AUTH_JSON` must contain the full JSON payload from your Codex CLI auth file.
Keepalive Codex runs fail without it.

```bash
# Validate local auth file and set secret in one step
test -f ~/.codex/auth.json
gh secret set CODEX_AUTH_JSON \
  --repo stranske/<your-repo> \
  --body "$(cat ~/.codex/auth.json)"
```

Verify secret exists:

```bash
gh secret list --repo stranske/<your-repo> | grep CODEX_AUTH_JSON
```

### 3.2.3 Claude CLI Secrets (`CLAUDE_CODE_OAUTH_TOKEN` / `CLAUDE_AUTH_JSON`)

Claude-run workflows (for example `reusable-claude-run.yml`) require one of:

- Preferred: `CLAUDE_CODE_OAUTH_TOKEN`
- Fallback: `CLAUDE_AUTH_JSON`

Set the preferred token:

```bash
# Generates/refreshes a long-lived token and writes it directly to the repo secret
gh secret set CLAUDE_CODE_OAUTH_TOKEN \
  --repo stranske/<your-repo> \
  --body "$(claude setup-token)"
```

Fallback using auth JSON:

```bash
# If you maintain a claude auth JSON export locally
gh secret set CLAUDE_AUTH_JSON \
  --repo stranske/<your-repo> \
  --body "$(cat /path/to/claude-auth.json)"
```

Verify at least one exists:

```bash
gh secret list --repo stranske/<your-repo> | grep -E "CLAUDE_CODE_OAUTH_TOKEN|CLAUDE_AUTH_JSON"
```

> **Important**: `WORKFLOWS_APP_ID` and `WORKFLOWS_APP_PRIVATE_KEY` are essential for
> keepalive automation. While workflows have PAT fallback logic, the keepalive system
> requires GitHub App tokens for proper authentication and rate limits.

### 3.3 Required Variables

Navigate to: **Settings** → **Secrets and variables** → **Actions** → **Variables**

| Variable Name | Description | Example Value |
|---------------|-------------|---------------|
| `ALLOWED_KEEPALIVE_LOGINS` | GitHub usernames allowed to trigger keepalive | `stranske` |
| `USE_CONSOLIDATED_WORKFLOWS` | Use the consolidated `agents-80-pr-event-hub.yml` + `agents-81-gate-followups.yml` hubs instead of the legacy split workflows. Set `true` for all new repos. | `true` |

Add the variables:
- [ ] `ALLOWED_KEEPALIVE_LOGINS` — Comma-separated list of usernames
- [ ] `USE_CONSOLIDATED_WORKFLOWS=true` — recommended for all new repos

### 3.3.1 Workflow Token Permissions (CRITICAL)

> **Critical**: GitHub creates new repos with `default_workflow_permissions=read`,
> which causes Gate to fail with `startup_failure` before any job runs (the
> `Gate / gate` commit status job needs `write` to publish the status). Every
> consumer repo must be flipped to `write` before its first PR runs through Gate.

**Symptom if skipped:** Gate workflow shows `startup_failure` (or shows the file
path `.github/workflows/pr-00-gate.yml` instead of `Gate` as the run name
because the workflow file can't even be parsed under the restricted permissions).
The `agents-81-gate-followups.yml` hub then skips the keepalive dispatch because
Gate never succeeded, and the entire automation pipeline is silently blocked.

**One-shot fix via gh CLI:**

```bash
gh api -X PUT /repos/<owner>/<repo>/actions/permissions/workflow \
  -F default_workflow_permissions=write \
  -F can_approve_pull_request_reviews=true
```

**Verify:**

```bash
gh api /repos/<owner>/<repo>/actions/permissions/workflow
# Expect: {"default_workflow_permissions":"write","can_approve_pull_request_reviews":true}
```

**Or via the UI:** **Settings** → **Actions** → **General** → **Workflow permissions**
→ select **"Read and write permissions"** and check **"Allow GitHub Actions to
create and approve pull requests"** → **Save**.

Discovered during `stranske/learning-management-system` bootstrap (2026-05).
Counter_Risk, Inv-Man-Intake, Trend_Model_Project, etc. all have `write` per
their `actions/permissions/workflow` settings.

**Checklist:**

- [ ] `default_workflow_permissions=write` on this repo
- [ ] `can_approve_pull_request_reviews=true` on this repo

### 3.4 Install GitHub Apps on Repository

> **Critical**: Even if you've configured app secrets, each GitHub App must be
> explicitly granted access to this repository.

**Symptom if skipped:** Keepalive fails with `Failed to create token for "<repo-name>": Not Found`

Apps to verify:
- `WORKFLOWS_APP_ID` / `WORKFLOWS_APP_PRIVATE_KEY`
- `KEEPALIVE_APP_ID` / `KEEPALIVE_APP_PRIVATE_KEY` (if set)

**Steps to install:**

1. Go to: **Settings** → **Applications** → **Installed GitHub Apps**
   - Direct link: https://github.com/settings/installations
   
2. Find each GitHub App in the list (matching the App IDs in your secrets)

3. Click **"Configure"** button on the right side of that row

4. Under **"Repository access"** section:
   - If **"All repositories"** is selected: You're done ✅
   - If **"Only select repositories"** is selected:
     - Click the **"Select repositories"** dropdown
     - Add your new repository to the list
     - Click **"Save"**

**Verify installation:**
- Go to: `https://github.com/stranske/<your-repo>/settings/installations`
- Confirm your GitHub App is listed there

**Checklist:**
- [ ] Workflows app has access to this repository
- [ ] Keepalive app has access to this repository (if configured separately)

> **Note**: This is separate from repository secrets. Secrets tell workflows which App 
> credentials to use, but the App itself must be installed on the repository to grant 
> access. New repositories are NOT automatically included if using "Only select repositories" mode.

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
- [ ] Workflow files reference `stranske/Workflows@v1` (or a pinned tag/SHA)


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
  https://raw.githubusercontent.com/stranske/Workflows/v1/.github/workflows/agents-63-issue-intake.yml

# Copy orchestrator with numbered naming  
curl -o .github/workflows/agents-70-orchestrator.yml \
  https://raw.githubusercontent.com/stranske/Workflows/v1/templates/consumer-repo/.github/workflows/agents-orchestrator.yml

# Optional: add a local sync-check workflow if your org maintains one.
# If you already have a maintained local sync workflow in another repo, adapt this pattern:
# curl -o .github/workflows/maint-sync-workflows.yml \
#   https://raw.githubusercontent.com/<owner>/<repo>/<ref>/.github/workflows/maint-sync-workflows.yml
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
> When copying workflow files, watch for local reusable-workflow references like:
>
> ```yaml
> uses: ./.github/workflows/reusable-agents-issue-bridge.yml
> ```
>
> This works in the Workflows repo but can break in consumer repos if the reusable workflow
> is not present locally. Prefer a remote reference instead:
>
> ```yaml
> uses: stranske/Workflows/.github/workflows/reusable-agents-issue-bridge.yml@v1
> ```
>
> **Preferred**: copy from the consumer template in this repo (already wired for consumer usage):
>
> ```bash
> curl -o .github/workflows/agents-issue-intake.yml \
>   https://raw.githubusercontent.com/stranske/Workflows/v1/templates/consumer-repo/.github/workflows/agents-issue-intake.yml
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
- [ ] `.python-version` file specifies Python version (e.g., `3.12`)

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
- `.gitignore` entries for `codex-prompt*.md`, `codex-output*.md`, `verifier-context.md`

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

**Common Non-Issues to Expect:**

> Don't be alarmed by these expected behaviors:

- **"PR number unavailable" warning** — Expected during PR creation, not an error
- **Multiple workflow attempts** — Retry logic is normal, check final run status
- **Workflows showing "in_progress"** — Wait for completion before troubleshooting
- **First keepalive run may fail** — If Codex CLI has issues, check logs; the
  automation pipeline itself (comment detection, workflow triggers, orchestration)
  should work correctly even if the Codex execution fails

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
- `WORKFLOWS_APP_ID` (required for keepalive)
- `WORKFLOWS_APP_PRIVATE_KEY` (required for keepalive)

### Required Variables

- `ALLOWED_KEEPALIVE_LOGINS`

---

## Phase 10: Register for Automatic Sync (Recommended)

> **Critical**: Your repo needs to be registered in **THREE** sync workflows to
> receive all updates. Missing any of these means missing important updates.

To receive automatic updates when workflow templates, documentation, and tool
versions change, add your repo to these three workflows:

### 10.1 Workflow & Script Sync

1. Add your repo to `REGISTERED_CONSUMER_REPOS` in:
   - File: `.github/workflows/maint-68-sync-consumer-repos.yml`
   - Purpose: Syncs workflow files, scripts, and prompts

   ```yaml
   REGISTERED_CONSUMER_REPOS: |
     stranske/Travel-Plan-Permission
     stranske/your-repo  # Add your repo here
   ```

- [ ] Added to `maint-68-sync-consumer-repos.yml`

### 10.2 Label Documentation Sync

2. Add your repo to `DEFAULT_CONSUMER_REPOS` in:
   - File: `.github/workflows/maint-65-sync-label-docs.yml`
   - Purpose: Syncs `docs/LABELS.md` to keep label documentation consistent

   ```yaml
   DEFAULT_CONSUMER_REPOS: |
     stranske/Travel-Plan-Permission
     stranske/your-repo  # Add your repo here
   ```

- [ ] Added to `maint-65-sync-label-docs.yml`

### 10.3 Dev Tool Version Sync

3. Add your repo to `REGISTERED_CONSUMER_REPOS` in:
   - File: `.github/workflows/maint-52-sync-dev-versions.yml`
   - Purpose: Syncs `autofix-versions.env` (ruff, black, mypy versions)

   ```yaml
   REGISTERED_CONSUMER_REPOS: |
     stranske/Travel-Plan-Permission
     stranske/your-repo  # Add your repo here
   ```

- [ ] Added to `maint-52-sync-dev-versions.yml`

### 10.4 Verify Sync Works

Test that sync workflows can access your repo:

```bash
# Test workflow sync
gh workflow run "Maint 68 Sync Consumer Repos" \
  --repo stranske/Workflows \
  -f repos="stranske/<your-repo>" \
  -f dry_run=true

# Test label doc sync
gh workflow run "Maint 65 Sync Label Docs" \
  --repo stranske/Workflows \
  -f repos="stranske/<your-repo>" \
  -f dry_run=true

# Test version sync
gh workflow run "Maint 52 Sync Dev Versions" \
  --repo stranske/Workflows \
  -f repos="stranske/<your-repo>" \
  -f dry_run=true
```

- [ ] All three sync workflows tested successfully

**Note**: Repos with custom Gate workflows should still be registered—only
the thin caller workflows are synced, not custom implementations.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
