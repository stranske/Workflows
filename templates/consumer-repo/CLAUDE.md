# CLAUDE.md - Consumer Repository Context

> **READ THIS FIRST** before making workflow changes.

## This is a Consumer Repo

This repository uses the **stranske/Workflows** workflow library. Most workflow logic lives there, not here.

**DO NOT** modify agent workflow files directly - they are synced from Workflows and will be overwritten.

## Architecture

```
stranske/Workflows (central library)
    │
    │ reusable workflows called via:
     │ uses: stranske/Workflows/.github/workflows/reusable-*.yml@v1
    │
    ▼
This Repo (consumer)
    .github/workflows/
      ├── agents-*.yml      → SYNCED from Workflows (don't edit)
      ├── autofix.yml       → SYNCED from Workflows (don't edit)
      ├── pr-00-gate.yml    → SYNCED but customizable
      ├── ci.yml            → REPO-SPECIFIC (can edit)
      └── autofix-versions.env → REPO-SPECIFIC (can edit)
```

## Which Files Can Be Edited

| File | Editable? | Notes |
|------|-----------|-------|
| `ci.yml` | ✅ Yes | Repo-specific CI configuration |
| `autofix-versions.env` | ✅ Yes | Repo-specific dependency versions |
| `pr-00-gate.yml` | ⚠️ Careful | Synced, but can customize if needed |
| `agents-*.yml` | ❌ No | Synced from Workflows |
| `autofix.yml` | ❌ No | Synced from Workflows |

## Keepalive System

When an issue is labeled `agent:codex`:
1. `agents-63-issue-intake.yml` creates a PR with bootstrap file
2. `agents-keepalive-loop.yml` runs Codex in iterations
3. Codex works through tasks in PR body until all complete

**Key prompts** (in `.github/codex/prompts/`):
- `keepalive_next_task.md` - Normal work instructions
- `fix_ci_failures.md` - CI fix instructions

## Common Issues

### Workflow fails with "workflow file issue"
- A reusable workflow is being called that doesn't exist
- Check Workflows repo has the required `reusable-*.yml` file
- Consumer workflows call INTO Workflows repo, not local files

### Agent not picking up changes
- Check PR has `agent:codex` label
- Check Gate workflow passed (green checkmark)
- Check PR body has unchecked tasks

### Need to update agent workflows
- DON'T edit locally - changes will be overwritten
- Fix in Workflows repo → sync will propagate here
- Or request manual sync: `gh workflow run maint-68-sync-consumer-repos.yml --repo stranske/Workflows`

## Reference Implementation

**Travel-Plan-Permission** is the reference consumer repo. When debugging:
1. Check if it works there first
2. Compare this repo's `.github/` with Travel-Plan-Permission
3. Look for missing files or differences

## Workflows Documentation

For detailed docs, see **stranske/Workflows**:
- `docs/INTEGRATION_GUIDE.md` - How consumer repos work
- `docs/keepalive/GoalsAndPlumbing.md` - Keepalive system design
- `docs/keepalive/SETUP_CHECKLIST.md` - Required files and secrets

## Quick Debug Commands

```bash
# Compare workflows with reference repo
diff .github/workflows/autofix.yml \
     <(gh api repos/stranske/Travel-Plan-Permission/contents/.github/workflows/autofix.yml --jq '.content' | base64 -d)

# Check for missing files
gh api repos/stranske/Travel-Plan-Permission/contents/.github/workflows --jq '.[].name' | sort > /tmp/tpp.txt
ls .github/workflows/ | sort > /tmp/here.txt
diff /tmp/tpp.txt /tmp/here.txt

# Trigger workflow sync from Workflows repo
gh workflow run maint-68-sync-consumer-repos.yml --repo stranske/Workflows
```

---

## �� POLICY: Cross-Repo Work

> **CRITICAL**: Read this before ANY work that might affect the Workflows repo.

### Policy Checkpoint Trigger

When creating a todo list, ask:

**"Does this work need changes in stranske/Workflows?"**

Signs that you need Workflows changes:
- Adding a new agent capability
- Modifying how keepalive/autofix/verifier works
- Needing a new Codex prompt
- Bug in a reusable workflow

### If YES → Work in Workflows First

1. Clone/checkout stranske/Workflows
2. Make changes there (following Workflows CLAUDE.md policy)
3. Ensure sync manifest is updated
4. Trigger sync to propagate to this repo
5. Then verify in this repo

**DO NOT** try to fix Workflows issues by editing local files - they will be overwritten on next sync.

### Add Policy Verification Todo

When your todo list involves cross-repo coordination, add as **FINAL** item:

```
✅ Verify cross-repo policy compliance:
   - [ ] Changes made in correct repo (Workflows vs Consumer)
   - [ ] Sync triggered if needed
   - [ ] Both repos have passing CI
```

### Quick Commands

```bash
# Check if a file is synced (compare to template)
diff .github/workflows/agents-keepalive-loop.yml \
     <(gh api repos/stranske/Workflows/contents/templates/consumer-repo/.github/workflows/agents-keepalive-loop.yml --jq '.content' | base64 -d)

# Trigger sync from Workflows
gh workflow run maint-68-sync-consumer-repos.yml --repo stranske/Workflows -f repos="${{ github.repository }}"

# Check sync manifest for what SHOULD be here
gh api repos/stranske/Workflows/contents/.github/sync-manifest.yml --jq '.content' | base64 -d
```
