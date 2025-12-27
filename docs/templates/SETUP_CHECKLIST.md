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

3. Update `.gitignore` to include:
   ```
   # Codex working files (preserved via workflow artifacts, not git)
   codex-prompt.md
   codex-output.md
   verifier-context.md
   ```

4. **Custom Gate workflow**: If your repo doesn't use the standard Python CI
   structure (pyproject.toml + ruff + pytest), create a custom `pr-00-gate.yml`:
   - Must run your existing CI/tests
   - Must post `Gate / gate` commit status for keepalive to detect
   - See examples in trip-planner or Manager-Database repos

---

## Phase 2: Secrets and Access Configuration

> **Critical**: Keepalive automation will fail silently without these secrets.

### 2.1 Bot Collaborator Access

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

### 2.2 Required Secrets

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

### 2.2 Required Variables

Navigate to: **Settings** → **Secrets and variables** → **Actions** → **Variables**

| Variable Name | Description | Example Value |
|---------------|-------------|---------------|
| `ALLOWED_KEEPALIVE_LOGINS` | GitHub usernames allowed to trigger keepalive | `stranske` |

Add the variable:
- [ ] `ALLOWED_KEEPALIVE_LOGINS` — Comma-separated list of usernames

---

## Phase 3: Workflow Configuration

### 3.1 Verify Workflow Files

Check that these workflows exist in `.github/workflows/`:

| Workflow | Purpose | Critical for Keepalive |
|----------|---------|------------------------|
| `pr-00-gate.yml` | CI enforcement, posts commit status | **YES** |
| `agents-pr-meta.yml` | Detects keepalive comments | **YES** |
| `agents-70-orchestrator.yml` | Runs keepalive sweeps (every 30 min) | **YES** |
| `agents-63-issue-intake.yml` | Creates issues from Issues.txt | No |
| `autofix.yml` | Auto-fixes lint/format issues | No |
| `ci.yml` | Thin caller for Python CI | No |

- [ ] All workflow files present
- [ ] Workflow files reference `stranske/Workflows@main`

### 3.2 Critical Workflow Configuration

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

## Phase 4: Scripts Configuration

### 4.1 Required JavaScript Scripts

These scripts MUST exist in `.github/scripts/`:

| Script | Purpose | Required By |
|--------|---------|-------------|
| `issue_pr_locator.js` | Finds PRs linked to issues | Agent bridge |
| `issue_context_utils.js` | Issue context helpers | Agent bridge |
| `issue_scope_parser.js` | Parses scope from issue body | Agent bridge |
| `keepalive_instruction_template.js` | Generates keepalive instructions | Agent bridge |

- [ ] All 4 JS scripts present

### 4.2 Required Python Scripts

These scripts MUST exist in `.github/scripts/`:

| Script | Purpose | Required By |
|--------|---------|-------------|
| `decode_raw_input.py` | Decodes ChatGPT input | agents-63 chatgpt_sync |
| `parse_chatgpt_topics.py` | Parses topics from input | agents-63 chatgpt_sync |
| `fallback_split.py` | Fallback topic splitting | agents-63 chatgpt_sync |

- [ ] All 3 Python scripts present

### 4.3 Required Codex Prompts

These files MUST exist in `.github/codex/` for the keepalive pipeline:

| File | Purpose |
|------|---------|
| `AGENT_INSTRUCTIONS.md` | Security boundaries and operational guidelines for Codex |
| `prompts/keepalive_next_task.md` | Prompt template for keepalive iterations |

- [ ] `.github/codex/AGENT_INSTRUCTIONS.md` present
- [ ] `.github/codex/prompts/keepalive_next_task.md` present

> **Critical**: Without these files, the `reusable-codex-run.yml` workflow will
> fail with "Base prompt file not found".

### 4.4 Required Templates

Templates MUST exist in `.github/templates/`:

| Template | Purpose |
|----------|---------|
| `keepalive-instruction.md` | Instructions for Codex in keepalive rounds |

- [ ] Template file present

---

## Phase 5: Project Files

### 5.1 Issues.txt Format

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

### 5.2 Python Project Files

For Python projects, ensure:

- [ ] `pyproject.toml` exists with dependencies
- [ ] `src/` directory structure follows package conventions
- [ ] `tests/` directory exists with `conftest.py`
- [ ] `.python-version` file specifies Python version (e.g., `3.11`)

---

## Phase 6: Branch Protection (Optional but Recommended)

> **Note**: Configure branch protection AFTER your first successful PR to avoid
> blocking the initial setup.

### 6.1 Recommended Settings

Navigate to: **Settings** → **Branches** → **Add branch protection rule**

For the `main` branch:

- [ ] **Require a pull request before merging**
- [ ] **Require status checks to pass before merging**
  - [ ] Add required status check: `Gate / gate`
- [ ] **Require branches to be up to date before merging**
- [ ] **Do not allow bypassing the above settings** (optional, for strict enforcement)

---

## Phase 7: Testing the Setup

### 7.1 Test CI Workflow

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

### 7.2 Test Keepalive (After Gate Works)

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

## Phase 8: Register for Automatic Sync (Optional)

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
