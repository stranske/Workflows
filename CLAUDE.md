# CLAUDE.md - Workflows Repository Context

> **READ THIS FIRST** before making any changes to the workflow system.

## 🚨 NON-NEGOTIABLE: Code Quality Standards

**DO NOT work around, ignore, or rationalize away code quality issues just because they "predate your changes" or "were already there."**

This is unacceptable behavior. When you encounter lint errors, test failures, or validation issues:

1. **FIX THEM.** Not "note them for later." Not "check if they're pre-existing." FIX THEM.
2. **Pre-existing issues are usually YOUR recent mistakes anyway.** The validation ran clean before - if it's failing now, you broke it.
3. **"It was already broken" is NEVER an excuse.** Quality code requires fixing problems, not stepping over them.
4. **Running `git stash` to check "baseline" issues is a waste of time.** Just fix the damn code.

If pre-commit hooks, CI, or validation scripts fail:
- Read the error message
- Fix every issue listed
- Do not proceed until checks pass

**Leaving a mess because "you didn't make it" does not produce quality code. Clean up after yourself AND others.**

### ⚠️ EXCEPTION: `models: read` Permission

**DO NOT REMOVE `models: read` from workflow permissions**, even though actionlint reports it as invalid.

- This permission is **required for LangChain components** to function correctly
- actionlint doesn't recognize it because it's a newer GitHub permission scope
- **Removing this permission WILL BREAK the agent workflows**

If you see actionlint errors about `models: read`, you MUST use `SKIP_ACTIONLINT=1` to bypass the check:

```bash
SKIP_ACTIONLINT=1 git commit -m "your message"
```

### ⚠️ FAILURE TRIGGERS - Read This When You See Failures

**WHEN YOU SEE:** CI failure, lint error, test failure, merge blocked, workflow failed, checks failing

**STOP. DO NOT:**
- Report it as "needs separate attention"
- Say "this is a pre-existing issue"  
- Categorize it as "someone else's problem"
- Move on to the next task
- Summarize status and wait for instructions

**INSTEAD, IMMEDIATELY:**
- Investigate the failure
- Find the root cause
- Fix it
- Verify the fix works
- THEN continue

**If you report a failure without fixing it, you have failed at your job.**

### ✅ END-OF-TASK CHECKLIST - Run This Before Declaring Done

Before saying "done", "complete", "finished", or summarizing results:

1. **Are there any failures I saw during this task?** If yes, go fix them.
2. **Did I categorize anything as "pre-existing" or "unrelated"?** That's a cop-out. Go fix it.
3. **Are all CI checks passing?** If not, why am I stopping?
4. **Would I be proud to show this work?** If there are known issues I'm ignoring, the answer is no.

## Repository Purpose

This is the **central workflow library** for the stranske organization. It provides:
1. **Reusable workflows** - Called by consumer repos via `uses: stranske/Workflows/.github/workflows/reusable-*.yml@v1` (use `@main` only for unreleased testing)
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

### ⚠️ IMPORTANT: After Syncing, Use the Merge Workflow

> **🚨 CRITICAL**: Before updating any files in `.github/`, read [**Dual-Location Sync Gotcha Guide**](docs/guides/dual-location-sync-gotcha.md) to prevent consumers from receiving outdated versions!




**ALWAYS** use `Merge Sync PRs` workflow (maint-71-merge-sync-prs.yml) to:
- Auto-merge sync PRs that pass CI checks
- Close stale/duplicate sync PRs
- Report which repos have failing checks

```bash
# After triggering a sync, run this to merge the resulting PRs:
gh workflow run "Merge Sync PRs" --repo stranske/Workflows --ref main

# Check status:
gh run list --workflow="maint-71-merge-sync-prs.yml" --limit 1
```

**DO NOT** manually merge sync PRs with `gh pr merge --admin` - use the workflow.

## Keepalive System

⚠️ **CRITICAL**: Before working on keepalive, read [`docs/keepalive/Agents.md`](docs/keepalive/Agents.md) which points to the canonical contracts.

### Two Ways to Run Codex

**1. CLI Agent (Primary - Workflow-Based)**
- Triggered by `agents-keepalive-loop.yml` workflow after Gate completes
- Used for PRs with `agent:codex` label
- Runs directly via `reusable-codex-run.yml`
- Does NOT require `@codex` comments
- This is the MAIN keepalive system

**2. UI Agent (Backup - Comment-Based)**
- Triggered by `@codex` comments on PRs
- Uses `chatgpt-codex-connector` bot
- Only for manual interventions or when CLI agent is unavailable
- Should NOT be triggered by automation

### Flow Diagram

```
Issue labeled → agents-63-issue-intake.yml → Creates PR with agent:codex label
                                                    ↓
                                        agents-keepalive-loop.yml (CLI workflow)
                                                    ↓
                                        (evaluates: gate passed? tasks remain?)
                                                    ↓
                                        reusable-codex-run.yml (runs Codex CLI)
                                                    ↓
                                        Codex pushes → Gate runs → Loop continues
```

### Why the Orchestrator Skips CLI Agent Labels

The orchestrator (`agents-70-orchestrator.yml`) contains a "Codex keepalive sweep" that posts `@codex` instruction comments to idle PRs. However, it **intentionally skips** PRs with `agent:*` labels because:

1. CLI agents (like `agent:codex`) are triggered by the **keepalive loop workflow**, not comments
2. Posting `@codex` comments would trigger the UI backup agent
3. Having both CLI and UI agents work on the same PR would cause conflicts

**Code location**: `scripts/keepalive-runner.js` → `hasCliAgentLabel()` function

This is **working as designed**. If a PR with `agent:codex` isn't progressing, the issue is in the keepalive loop workflow, NOT the orchestrator.

**Key files for keepalive:**
- `.github/codex/prompts/keepalive_next_task.md` - Normal work prompt
- `.github/codex/prompts/fix_ci_failures.md` - CI fix prompt
- `.github/scripts/keepalive_instruction_template.js` - Prompt generation
- `docs/keepalive/GoalsAndPlumbing.md` - **Canonical contract** (READ THIS FIRST)
- `docs/keepalive/MULTI_AGENT_ROUTING.md` - Agent routing architecture
- `docs/keepalive/Agents.md` - Required reading before keepalive changes

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
Error calling workflow 'stranske/Workflows/.github/workflows/reusable.yml@v1'. 
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

### Systematic Discovery Protocol

**BEFORE making documentation changes or answering "what's missing":**

1. **Read ALL related documentation first** - Don't skip:
   ```bash
   # For keepalive/workflow questions:
   find docs/keepalive -name "*.md" -exec cat {} \;
   
   # For setup questions:
   cat docs/keepalive/SETUP_CHECKLIST.md docs/TMP_TRANSITION_PLAN.md
   
   # For any domain:
   grep -r "keyword1\|keyword2\|keyword3" docs/ --include="*.md"
   ```

2. **Check what EXISTS in practice** - Compare docs to reality:
   ```bash
   # Check reference consumer repo:
   gh api repos/stranske/Travel-Plan-Permission/contents/.github
   
   # Check template vs docs:
   cat templates/consumer-repo/.gitignore
   
   # Find validation scripts:
   ls scripts/*.py | xargs grep -l "sync\|validate\|check"
   ```

3. **Search for existing automation** - Don't recreate:
   ```bash
   # Look for canonical sources:
   grep -rn "canonical\|template\|source of truth" .
   
   # Look for validation tools:
   find scripts/ -name "*sync*" -o -name "*validate*"
   ```

4. **Always check for authentication methods**:
   ```bash
   # GitHub App configuration often missed:
   grep -rn "GitHub App\|WORKFLOWS_APP\|APP_ID\|PRIVATE_KEY" docs/
   grep -rn "authentication\|secrets" docs/keepalive/SETUP_CHECKLIST.md
   ```

5. **Reference, don't duplicate**:
   - ❌ Copy patterns from template into docs → maintenance burden
   - ✅ Reference template path + provide validation command
   - ❌ Recreate what exists in scripts
   - ✅ Use existing scripts and document them

**Triggers**: Use this protocol when:
- User asks "what's missing from X"
- Making documentation changes
- Adding to setup guides
- Comparing template vs docs

**Why**: Prevents missing critical info (GitHub App), prevents duplication (gitignore patterns), ensures maintainability (reference canonical sources).

### Change Checklist

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

## ⚠️ CRITICAL: Issue Creation Standards

**BEFORE creating any GitHub issue, use the AGENT_ISSUE_TEMPLATE.**

Issues in this repo follow a strict format defined in [`docs/templates/AGENT_ISSUE_TEMPLATE.md`](docs/templates/AGENT_ISSUE_TEMPLATE.md).

### Required Sections

Every issue MUST have:

| Section | Purpose |
|---------|---------|
| **Tasks** | Actionable checkboxes (`- [ ]` format) for agent automation |
| **Acceptance Criteria** | Verifiable completion conditions with checkboxes |

### Recommended Sections

Every issue SHOULD have:

| Section | Purpose |
|---------|---------|
| **Why** | Motivation - explains why this matters |
| **Scope** | What this issue covers (boundaries) |
| **Non-Goals** | What is explicitly excluded |
| **Implementation Notes** | Files to create/modify, branch name, PR title |

### Issue Format Example

```markdown
## Why

[1-2 sentences explaining the motivation and value]

## Scope

[What this issue covers - be specific about deliverables]

## Non-Goals

- [What is explicitly NOT covered]
- [Prevent scope creep by listing exclusions]

## Tasks

- [ ] [First actionable task]
- [ ] [Second actionable task]
- [ ] [Continue with specific, checkable items]

## Acceptance Criteria

- [ ] [First verifiable condition]
- [ ] [Second verifiable condition]
- [ ] [How to confirm the issue is complete]

## Implementation Notes

Files to create/modify:
- `path/to/file.py`
- `path/to/other-file.yml`

Branch: `codex/issue-XXX`
PR title: `[Category] Short description of changes`
```

### Why This Matters

- **Agent automation**: Codex keepalive uses checkbox Tasks to track progress
- **Scope clarity**: Non-Goals prevent agents from over-engineering solutions
- **Verification**: Acceptance Criteria provide clear completion signals
- **Traceability**: Implementation Notes guide agents to correct files

### Common Mistakes

❌ **DON'T**: Create issues with only Priority/Estimate/Description
❌ **DON'T**: Use bullet points without checkboxes in Tasks
❌ **DON'T**: Skip Non-Goals (leads to scope creep)
❌ **DON'T**: Forget Implementation Notes (agents waste time finding files)

✅ **DO**: Follow the full template structure
✅ **DO**: Convert all bullet points in Tasks/Criteria to checkboxes
✅ **DO**: Be specific about files and branch names
✅ **DO**: Include "Part of #XXX" for issues in a series

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
