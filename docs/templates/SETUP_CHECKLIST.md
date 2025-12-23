# Consumer Repository Setup Checklist

This checklist guides you through setting up a new repository using the Workflows
template system. Follow each step carefully—**keepalive automation requires precise
configuration** and will fail silently if any element is missing.

> **Important**: It took approximately 25 PRs in the Travel-Plan-Permission repo
> before keepalive started functioning correctly. The lessons learned are encoded
> in this checklist.

---

## Prerequisites

Before starting, ensure you have:

- [ ] Access to [stranske/Workflows](https://github.com/stranske/Workflows) repository
- [ ] A GitHub PAT for `stranske-automation-bot` (for SERVICE_BOT_PAT)
- [ ] Admin access to create repository secrets and variables
- [ ] Python 3.11+ installed locally for testing

---

## Phase 1: Repository Creation

### 1.1 Create Repository from Template

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

---

## Phase 2: Secrets Configuration

> **Critical**: Keepalive automation will fail silently without these secrets.

### 2.1 Required Secrets

Navigate to: **Settings** → **Secrets and variables** → **Actions** → **Secrets**

| Secret Name | Description | Source |
|-------------|-------------|--------|
| `SERVICE_BOT_PAT` | PAT for stranske-automation-bot | Contact admin for token |
| `ACTIONS_BOT_PAT` | PAT for workflow dispatch | Same as SERVICE_BOT_PAT or dedicated |
| `OWNER_PR_PAT` | PAT for PR creation | Repository owner's PAT |

Add each secret:
- [ ] `SERVICE_BOT_PAT` — Required for orchestrator and agent workflows
- [ ] `ACTIONS_BOT_PAT` — Required for triggering workflows between repos
- [ ] `OWNER_PR_PAT` — Required for creating PRs from agent bridge

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

### 4.3 Required Templates

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

### Required Variables

- `ALLOWED_KEEPALIVE_LOGINS`

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-01 | Initial checklist based on Travel-Plan-Permission learnings |
