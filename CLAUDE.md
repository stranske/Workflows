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
│    pr-00-gate.yml        → REPO-SPECIFIC (not synced)            │
│    ci.yml                → REPO-SPECIFIC (not synced)            │
└─────────────────────────────────────────────────────────────────┘
```

## Consumer Repos

| Repo | Status | Notes |
|------|--------|-------|
| Travel-Plan-Permission | Reference | Gold standard - sync FROM here when debugging |
| Manager-Database | Consumer | Has custom Gate/CI workflows |
| Template | Consumer | Minimal Python template |
| trip-planner | Consumer | Has custom Gate/CI workflows |

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
| `autofix.yml` | `autofix.yml` | Lint/format auto-fix |

**NOT synced** (repo-specific):
- `pr-00-gate.yml` - Each repo has custom CI configuration
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
