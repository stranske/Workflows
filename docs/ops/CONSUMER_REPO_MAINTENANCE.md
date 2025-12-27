# Consumer Repository Maintenance Guide

This document outlines the process for maintaining workflow system consistency across consumer repositories and debugging issues that may affect multiple repos.

---

## Registered Consumer Repos

The following repos are automatically synced via `maint-68-sync-consumer-repos.yml`:

| Repository | Status | Notes |
|------------|--------|-------|
| `stranske/Template` | ✅ Registered | Source template for new repos |
| `stranske/Travel-Plan-Permission` | ✅ Registered | Primary test consumer |
| `stranske/trip-planner` | ⏳ Pending | Needs custom Gate (no pyproject.toml) |
| `stranske/Manager-Database` | ⏳ Pending | Needs custom Gate (docker compose, pre-commit) |

### Adding a New Consumer Repo

1. Add repo to `REGISTERED_CONSUMER_REPOS` in `maint-68-sync-consumer-repos.yml`
2. Ensure bot collaborator access (see [Bot Access](#bot-collaborator-access))
3. Run sync workflow manually to verify

### Repos with Custom Configurations

Some repos cannot use the template `pr-00-gate.yml` because:
- **trip-planner**: No `pyproject.toml`, uses `requirements.txt` + pytest
- **Manager-Database**: Uses `docker compose`, `pre-commit`, custom test setup

For these repos:
- Gate workflow is maintained locally (not synced)
- Other agent workflows ARE synced from templates
- Document customizations in repo's `.github/README.md`

---

## Bug Triage Process

When a bug is identified in workflow templates:

### Step 1: Classify the Bug

| Category | Scope | Example |
|----------|-------|---------|
| **Template bug** | All repos using template | Logical expression `|| 'true'` always true |
| **Reusable workflow bug** | All repos calling the workflow | Missing output parameter |
| **Consumer-specific** | Single repo | Wrong CI workflow name in verifier |

### Step 2: Assess Impact

```bash
# Check which repos have the affected file
for repo in Template Travel-Plan-Permission trip-planner Manager-Database; do
  echo "=== $repo ==="
  curl -s -H "Authorization: token $TOKEN" \
    "https://api.github.com/repos/stranske/$repo/contents/.github/workflows/FILENAME" | \
    jq -r '.content' | base64 -d | grep -E "PATTERN" | head -5
done
```

### Step 3: Fix Strategy

| Bug Type | Fix Location | Propagation |
|----------|-------------|-------------|
| Template bug | `templates/consumer-repo/` | Auto-sync to registered repos |
| Reusable workflow | `.github/workflows/reusable-*.yml` | Immediate (all callers) |
| Consumer-specific | Consumer repo directly | Manual PR |

### Step 4: Create Fix Tracking Issue

For bugs affecting multiple repos, create a tracking issue with:
- [ ] Bug description and root cause
- [ ] List of affected repos
- [ ] Fix commits/PRs for each location
- [ ] Verification steps

---

## Common Bug Patterns

### Logical Expression Bugs

**Pattern**: `${{ inputs.flag && 'true' || 'true' }}`  
**Problem**: Always evaluates to 'true', input cannot disable feature  
**Fix**: `${{ inputs.flag && 'true' || 'false' }}`

**Affected files** (historically):
- `agents-orchestrator.yml`: `enable_watchdog`, `enable_keepalive`
- `agents-issue-intake.yml`: `post_agent_comment`

### Missing Event Handlers

**Pattern**: Workflow has trigger but no corresponding job  
**Example**: `workflow_run` trigger without handler job  
**Detection**: Search for trigger in `on:` block, verify matching job exists

### Hardcoded Values

**Pattern**: Repository-specific values in templates  
**Examples**:
- `allowed_keepalive_logins: 'stranske'`
- `ci_workflows: '["ci.yml"]'`
- Bot account names in comments

**Fix**: Use variables or empty defaults with clear documentation

### Action Version Inconsistencies

**Pattern**: Mixed versions of same action across workflows  
**Example**: `actions/github-script@v7` in some files, `@v8` in others  
**Fix**: Standardize on single version, update all files together

---

## Bot Collaborator Access

The `stranske-automation-bot` account needs push access to consumer repos for:
- Autofix commits
- Agent-created PRs

### Checking Access

```bash
curl -s -H "Authorization: token $TOKEN" \
  "https://api.github.com/repos/stranske/REPO/collaborators/stranske-automation-bot/permission" | \
  jq '{permission}'
```

### Granting Access

```bash
curl -s -X PUT \
  -H "Authorization: token $TOKEN" \
  "https://api.github.com/repos/stranske/REPO/collaborators/stranske-automation-bot" \
  -d '{"permission": "push"}'
```

**Note**: The bot must accept the invitation. Check pending invitations at:
`https://github.com/notifications`

---

## Sync Workflow Details

### What Gets Synced

| File Type | Source | Synced? |
|-----------|--------|---------|
| Thin caller workflows | `templates/consumer-repo/.github/workflows/` | ✅ Yes |
| Codex prompts | `templates/consumer-repo/.github/codex/` | ✅ Yes |
| Issue templates | `templates/consumer-repo/.github/ISSUE_TEMPLATE/` | ✅ Yes |
| `autofix-versions.env` | N/A | ❌ No (repo-specific) |
| Custom Gate workflows | N/A | ❌ No (repo-specific) |

### Manual Sync Trigger

```bash
gh workflow run "Maint 68 Sync Consumer Repos" \
  --repo stranske/Workflows \
  -f repos="stranske/Travel-Plan-Permission" \
  -f dry_run=true
```

---

## Verification Checklist

After fixing a template bug:

- [ ] Fix applied to `templates/consumer-repo/`
- [ ] Fix applied to reusable workflow (if applicable)
- [ ] Sync workflow triggered or PR created for registered repos
- [ ] Unregistered repos identified and PRs created
- [ ] Bot review comments addressed in PRs
- [ ] CI passing in all affected repos

---

## Version History

| Date | Change |
|------|--------|
| 2025-12-27 | Initial document based on trip-planner/Manager-Database setup learnings |
