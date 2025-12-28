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
- Check `agents:pause` label is NOT present

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
