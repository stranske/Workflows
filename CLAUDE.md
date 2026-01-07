# CLAUDE.md - Workflows Repository Context

> **READ THIS FIRST** before making any changes to the workflow system.

## Repository Purpose

This is the **central workflow library** for the stranske organization. It provides:
1. **Reusable workflows** - Called by consumer repos via `uses: stranske/Workflows/.github/workflows/reusable-*.yml@main`
2. **Consumer repo templates** - Thin caller workflows synced to consumer repos
3. **Shared scripts** - JS/Python utilities used by workflows

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    stranske/Workflows                            │
│  (Central Library - source of truth)                            │
├─────────────────────────────────────────────────────────────────┤
│  .github/workflows/                                              │
│    reusable-*.yml        → Called by consumer repos              │
│    agents-*.yml          → Run here for self-testing             │
│    maint-68-sync-*.yml   → Syncs templates to consumers          │
│                                                                  │
│  templates/consumer-repo/.github/workflows/                      │
│    *.yml                 → SYNCED to consumer repos              │
├─────────────────────────────────────────────────────────────────┤
                              │
                              │ sync via maint-68-sync-consumer-repos.yml
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Consumer Repos (Travel-Plan-Permission, Manager-Database, etc) │
├─────────────────────────────────────────────────────────────────┤
│  .github/workflows/                                              │
│    agents-*.yml          → Thin callers (from templates)         │
│    ci.yml                → REPO-SPECIFIC (not synced)            │
└─────────────────────────────────────────────────────────────────┘
```

## Consumer Repos

| Repo | Status | Notes |
|------|--------|-------|
| Travel-Plan-Permission | Reference | Gold standard - compare TO here when debugging |
| Manager-Database | Consumer | Has custom ci.yml |
| Template | Consumer | Minimal Python template |
| trip-planner | Consumer | Has custom ci.yml |

## Key Workflows

### Reusable Workflows (in `.github/workflows/`)

| Workflow | Purpose | Called By |
|----------|---------|-----------|
| `reusable-10-ci-python.yml` | Python CI (lint, test, mypy) | Consumer ci.yml/pr-00-gate.yml |
| `reusable-18-autofix.yml` | Auto-fix lint/format issues | Consumer autofix.yml |
| `reusable-agents-issue-bridge.yml` | Bootstrap PRs from issues | Consumer agents-63-issue-intake.yml |
| `reusable-70-orchestrator-*.yml` | Keepalive orchestration | Consumer agents-70-orchestrator.yml |
| `reusable-codex-run.yml` | Execute Codex agent | Orchestrator |

### Consumer Workflow Templates (in `templates/consumer-repo/.github/workflows/`)

These get **synced** to consumer repos via `maint-68-sync-consumer-repos.yml`:

| Template | Consumer File | Purpose |
|----------|---------------|---------|
| `agents-issue-intake.yml` | `agents-63-issue-intake.yml` | Convert labeled issues to PRs |
| `agents-keepalive-loop.yml` | `agents-keepalive-loop.yml` | Keepalive iteration loop |
| `agents-orchestrator.yml` | `agents-70-orchestrator.yml` | Scheduled orchestration |
| `agents-pr-meta.yml` | `agents-pr-meta.yml` | PR comment/dispatch handling |
| `agents-verifier.yml` | `agents-verifier.yml` | PR verification checks |
| `agents-bot-comment-handler.yml` | `agents-bot-comment-handler.yml` | Address bot review comments |
| `autofix.yml` | `autofix.yml` | Lint/format auto-fix |
| `pr-00-gate.yml` | `pr-00-gate.yml` | PR gate (synced but customizable) |

**NOT synced** (repo-specific):
- `autofix-versions.env` - Each repo maintains its own dependency versions
- `ci.yml` - Each repo has custom CI configuration

## Sync Mechanism

1. Changes to `templates/consumer-repo/**` trigger `maint-68-sync-consumer-repos.yml`
2. Sync creates PRs in each consumer repo listed in `REGISTERED_CONSUMER_REPOS`
3. Consumer repos: Travel-Plan-Permission, Template, trip-planner, Manager-Database

**Before syncing**, ensure files pass consumer-repo lint rules (ruff with UP, SIM).

## Keepalive System

The keepalive loop keeps Codex working on a PR until all tasks are complete:

```
Issue labeled → agents-63-issue-intake.yml → Creates PR with agent:codex label
                                                    ↓
                                        agents-keepalive-loop.yml
                                                    ↓
                                        (evaluates: gate passed? tasks remain?)
                                                    ↓
                                        reusable-codex-run.yml (runs Codex)
                                                    ↓
                                        Codex pushes → Gate runs → Loop continues
```

**Key files for keepalive:**
- `.github/codex/prompts/keepalive_next_task.md` - Normal work prompt
- `.github/codex/prompts/fix_ci_failures.md` - CI fix prompt
- `.github/scripts/keepalive_instruction_template.js` - Prompt generation

## Secrets

| Secret | Purpose | Used By |
|--------|---------|---------|
| `SERVICE_BOT_PAT` | Bot account for comments/labels | All agent workflows |
| `OWNER_PR_PAT` | PR creation on behalf of owner | Issue bridge |
| `GH_APP_ID` / `GH_APP_PRIVATE_KEY` | GitHub App auth (preferred) | All workflows |

Secrets use **lowercase** in `workflow_call` definitions but reference org secrets.

## Common Debugging Patterns

### startup_failure - Invalid Workflow File

**CRITICAL: When a workflow shows `startup_failure`, the error message is ONLY visible in the Annotations section of the GitHub UI.**

Startup failures mean the workflow YAML is invalid. There are NO job logs because the workflow never started. The gh CLI cannot retrieve these error messages via API.

**How to get the error message:**

```bash
# 1. Get the run URL
gh run view RUN_ID --repo owner/repo --json html_url --jq '.html_url'

# 2. Open in browser - ERROR IS AT THE TOP IN ANNOTATIONS SECTION
"$BROWSER" "URL"
```

**Common startup_failure causes:**
- **Permission conflicts**: Nested jobs in reusable workflows requesting more permissions than caller grants
- Invalid YAML syntax
- Referencing non-existent reusable workflows
- Invalid job/step references
- Type mismatches in inputs

**Example error:**
```
Error calling workflow 'stranske/Workflows/.github/workflows/reusable.yml@main'. 
The nested job 'job_name' is requesting 'contents: write', but is only allowed 'contents: read'.
```

**Solution:** When calling reusable workflows with explicit permissions, those become the MAXIMUM permissions any nested job can have. Grant sufficient permissions in the caller workflow.

### "Workflow file issue" with no logs
- Usually means a reusable workflow is missing
- Check that `uses: ./.github/workflows/reusable-*.yml` files exist in the repo
- Consumer repos call into Workflows repo, not local reusable files

### Consumer repo workflow fails but works in Travel-Plan-Permission
- Check if the consumer is missing a required file (script, template, workflow)
- Compare `.github/` directories between repos
- Run `maint-68-sync-consumer-repos.yml` to sync latest templates

### Keepalive not triggering
- Check PR has `agent:codex` label
- Check Gate workflow passed
- Check PR body has unchecked tasks in Automated Status Summary
- Check `agents:paused` label is NOT present

## Documentation Index

**Read these for deeper understanding:**

| Document | Purpose |
|----------|---------|
| `docs/STRUCTURE.md` | Repository file structure |
| `docs/INTEGRATION_GUIDE.md` | How to integrate consumer repos |
| `docs/keepalive/GoalsAndPlumbing.md` | Keepalive system design |
| `docs/keepalive/SETUP_CHECKLIST.md` | Consumer repo setup steps |
| `docs/keepalive/KEEPALIVE_TROUBLESHOOTING.md` | Debugging keepalive |

## Before Making Changes

1. **Read the relevant doc** from the index above
2. **Check Travel-Plan-Permission** as the reference implementation
3. **Test in Workflows repo first** before syncing to consumers
4. **Run pre-sync validation** to ensure files pass consumer lint rules
5. **Sync to ALL consumer repos** to maintain consistency

## ⚠️ CRITICAL: Always Sync with Main Before Creating PRs

**BEFORE creating any PR, ALWAYS sync your branch with the latest main to avoid conflicts.**

### Required Process:

```bash
# Before creating a PR, ALWAYS run:
git fetch origin main
git merge origin/main
# OR
git rebase origin/main
```

### Why This Matters:

1. **Prevents merge conflicts** - Main may have moved forward since you branched
2. **Ensures your changes work with latest code** - CI failures from stale base
3. **Avoids blocking auto-merge** - Conflicts prevent automatic merging
4. **Saves time** - Fixing conflicts after PR creation wastes CI resources

### When to Sync:

- ✅ **ALWAYS** before running `gh pr create`
- ✅ After main has merged other PRs while you're working
- ✅ Before pushing a feature branch that's been worked on locally
- ✅ When you see "This branch is X commits behind main"

### Red Flags (You Forgot to Sync):

- ❌ PR shows "CONFLICTING" merge status
- ❌ PR shows "This branch is out-of-date with the base branch"
- ❌ Auto-merge fails with "branch must not be behind the base branch"
- ❌ GitHub shows conflict markers in PR files view

### Recovery:

If you forgot to sync and created a PR with conflicts:

```bash
# On your feature branch:
git fetch origin main
git merge origin/main
# Resolve any conflicts in files
git add <conflicted-files>
git commit -m "Merge main and resolve conflicts"
git push
```

**Make this second nature:** Before every `gh pr create`, run `git fetch origin main && git merge origin/main`.

## ⚠️ CRITICAL: Agent Bot Review Comments

**BEFORE merging any PR, check for and address ALL agent bot comments.**

Agent bots (like `copilot-pull-request-reviewer`) analyze code and flag:
- Standards violations (line length, encoding, etc.)
- Logic errors (redundant conditions, incorrect defaults)
- Best practices (cross-platform compatibility, error handling)
- Repository inconsistencies (mismatched configs)

**These comments are NOT suggestions - they are issues that MUST be fixed.**

### Process for Bot Comments

```bash
# 1. Check PR for bot comments
gh pr view <PR_NUMBER> --repo stranske/Workflows --comments

# 2. For each unresolved comment:
#    - Evaluate if valid (assume yes unless proven wrong)
#    - Implement the fix
#    - Test the change
#    - Commit with clear explanation

# 3. Do NOT merge until all bot comments are resolved or explicitly dismissed with justification

# 4. If bot suggests code change, USE the suggested code unless there's a technical reason not to
```

### Why This Matters

- Bot comments often catch issues that break consumer repos
- One ignored comment = potential bugs in 7+ repos after sync
- Bots enforce repository standards (line-length, encoding, etc.)
- Standards violations fail CI in consumer repos

### Examples of Critical Bot Catches

- Wrong default parameter values that don't match repo config
- Missing encoding specifications that cause Windows failures
- Redundant logic that indicates misunderstanding
- Line length violations that fail linter checks

**If you disagree with a bot comment:**
1. Explain why in PR comment
2. Tag the bot comment as "won't fix" with justification
3. Document the decision in code comments if needed
4. Do NOT silently ignore

## ⚠️ CRITICAL: Template Changes (READ THIS!)

**If you modify `templates/consumer-repo/` YOU WILL SYNC TO ALL CONSUMER REPOS.**

Before editing any template file:

```bash
# 1. Validate YAML syntax and style
python3 scripts/validate_workflow_yaml.py templates/consumer-repo/.github/workflows/*.yml

# 2. Check against repo standards (line-length = 100)
ruff check templates/consumer-repo/

# 3. Dry-run the sync to see impact
gh workflow run maint-68-sync-consumer-repos.yml -f dry_run=true
```

**Template changes will trigger PRs in 4+ consumer repos. One mistake = 4+ failing CI runs.**

Repo standards (from pyproject.toml):
- Line length: **100 characters**
- Format: black, ruff, isort
- All templates must pass validation before commit

## ⚠️ CRITICAL: New Workflow Artifact Check

**BEFORE adding any new workflow, check if it creates files that should be in .gitignore:**

```bash
# 1. Review workflow for file creation
grep -E "write|create|output|artifact" .github/workflows/your-workflow.yml

# 2. Check if workflow writes to working directory
# Look for: >, >>, tee, echo >>, python open(), write_file, etc.

# 3. Common artifacts that MUST be in .gitignore:
# - Status files: *-status.json, *-report.json, *-summary.json
# - Temp files: *.tmp, *.temp, .cache/, tmp/
# - Agent files: codex-output.md, verifier-context.md
# - Build artifacts: dist/, build/, .artifacts/

# 4. Test the workflow and check git status
gh workflow run your-workflow.yml
# Wait for completion, then:
git status --ignored

# 5. Add any new artifacts to .gitignore BEFORE syncing templates
```

**Why this matters:**
- Workflows that create tracked files → merge conflicts in consumer repos
- Auto-generated files in git → hours of debugging conflict resolution
- One forgotten artifact file → 7+ repos with conflicts

## Quick Commands

```bash
# List consumer repos
echo "$REGISTERED_CONSUMER_REPOS"

# Check what gets synced
ls templates/consumer-repo/.github/workflows/

# Manually trigger sync (dry run)
gh workflow run maint-68-sync-consumer-repos.yml -f dry_run=true

# Compare consumer with template
diff templates/consumer-repo/.github/workflows/autofix.yml \
     <(gh api repos/stranske/Travel-Plan-Permission/contents/.github/workflows/autofix.yml --jq '.content' | base64 -d)
```

---

## 🔴 POLICY ENFORCEMENT: Sync Artifacts

> **CRITICAL**: This section enforces the sync policy. Read before creating ANY todo list.

### Policy Checkpoint Trigger

When creating a todo list, ALWAYS ask yourself:

**"Does this work involve creating or modifying artifacts that consumers need?"**

Artifacts include:
- Workflows (`.github/workflows/*.yml`)
- Codex prompts (`.github/codex/prompts/*.md`)
- Scripts (`.github/scripts/*.js`, `.github/scripts/*.py`)
- Documentation synced to consumers

### If YES → Add Policy Verification Todo

Add this item as the **FINAL** todo in your list:

```
✅ Verify sync policy compliance:
   - [ ] New files added to .github/sync-manifest.yml
   - [ ] New files copied to templates/consumer-repo/
   - [ ] Validation CI passes
```

### Sync Manifest Location

All sync-able files MUST be declared in: **`.github/sync-manifest.yml`**

This manifest is the **single source of truth**. The sync workflow reads from it.
The validation CI (`health-70-validate-sync-manifest.yml`) enforces completeness.

### File Categorization

| File Pattern | Category | Sync Behavior |
|--------------|----------|---------------|
| `reusable-*.yml` | Reusable | NOT synced - called via `uses:` |
| `maint-*.yml` | Maintenance | NOT synced - Workflows-only |
| `health-*.yml` | Health checks | NOT synced - Workflows-only |
| `selftest-*.yml` | Self-tests | NOT synced - Workflows-only |
| `agents-*.yml` | Agent workflows | SYNCED - must be in manifest |
| `autofix.yml` | Autofix | SYNCED - must be in manifest |
| `pr-00-gate.yml` | Gate | SYNCED - must be in manifest |
| `*.md` in codex/prompts | Prompts | SYNCED - must be in manifest |

### Example: Adding a New Agent Workflow

1. Create workflow in `.github/workflows/agents-new-feature.yml`
2. Copy to `templates/consumer-repo/.github/workflows/agents-new-feature.yml`
3. Add to `.github/sync-manifest.yml`:
   ```yaml
   workflows:
     - source: .github/workflows/agents-new-feature.yml
       description: "New feature workflow"
   ```
4. Run validation: `gh workflow run health-70-validate-sync-manifest.yml`
5. Trigger sync: `gh workflow run maint-68-sync-consumer-repos.yml`

### Why This Matters

Without this policy:
- New features work in Workflows but silently fail in consumer repos
- Hours of debugging "why doesn't X work in Manager-Database?"
- Repeated failures of the same category

With this policy:
- CI fails if you forget to declare sync-able files
- Single source of truth (manifest) prevents drift
- Clear enforcement at PR time, not after deployment
