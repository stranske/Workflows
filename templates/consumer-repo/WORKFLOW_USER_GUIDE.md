# Workflow User Guide

**Source:** [Workflows Repository](https://github.com/stranske/Workflows)

This guide explains how to use the automated workflows in your repository. The central Workflows repository distributes shared workflows. Each consumer also owns its repository-specific configuration.

---

## Table of Contents

1. [Quick Start: Most Common Workflows](#quick-start-most-common-workflows)
2. [Label Reference](#label-reference)
3. [Workflow Triggers Summary](#workflow-triggers-summary)
4. [Complete Feature Reference](#complete-feature-reference)
5. [Troubleshooting](#troubleshooting)
6. [Advanced Usage](#advanced-usage)

---

## Quick Start: Most Common Workflows

### 1. Get AI Help on an Issue → Create a PR

**Use Case:** You have an issue that needs code changes

**Steps:**
1. Create or open an issue with a clear description
2. Add label: `agents:optimize` (AI analyzes and suggests improvements)
3. Review the suggestions comment
4. Add label: `agents:apply-suggestions` (applies formatting)
5. Add label: `agent:codex` (creates a PR automatically)

**What Happens:**
- Issue is analyzed for clarity and completeness
- Issue is formatted to standard template
- Codex agent creates a branch and opens a ready-for-review PR
- Agent works through the tasks automatically
- Keepalive monitors and continues work until complete
- Verification runs after merge

**Time:** 5-30 minutes depending on complexity

**Example:**
```
Issue: "Add user authentication"
→ Add `agents:optimize`
→ Review suggestions
→ Add `agents:apply-suggestions` 
→ Add `agent:codex`
→ PR created in ~2 minutes
```

---

### 2. Auto-Fix Failing CI on Your PR

**Use Case:** Your PR has formatting or lint errors

**Steps:**
1. Add label: `autofix` to your PR
2. Wait ~2 minutes for workflow to run
3. Check for new commits with fixes

**What Gets Fixed:**
- Code formatting (black, prettier, etc.)
- Import organization
- Trailing whitespace
- Basic type annotation issues
- Lint errors that can be auto-corrected

**Advanced:** Use `autofix:clean` for more aggressive fixes including cosmetic repairs

**Time:** 1-3 minutes

---

### 3. Start Work Directly From a PR

**Use Case:** You are opening a PR without first creating a GitHub issue

**Steps:**
1. Fill out exactly one option in the PR template's `Workflow Source` section
2. If the PR came from an issue, include `Closes #123` or `Related to #123`
3. If there is no issue, choose the direct, local request, automation, review follow-up, sync/maintenance, or Dependabot source
4. Use a `workflow:source-*` label if you need to classify an existing PR from the PR list

**What Happens:**
- Workflows treats valid non-issue sources as intentional work instead of missing process state
- PR metadata automation avoids repeated missing-source repair comments
- Keepalive can continue without a linked issue when the PR has a valid non-issue workflow source context

**Common labels:**
- `workflow:source-direct-pr`
- `workflow:source-local-request`
- `workflow:source-review-followup`
- `workflow:source-sync`
- `workflow:source-dependabot`
- `workflow:no-automation`

---

### 4. End-to-end automation

Use the [shared opener and closer](https://github.com/stranske/Workflows/blob/main/docs/ops/LOCAL_LANES.md#lanes-overview) for eligible issues and guarded promotion. Follow the issue-linked PR for keepalive and post-merge verification.

---

## Label Reference

### User-Applied Labels (Triggers)

| Label | Where | What It Does |
|-------|-------|--------------|
| `autofix` | PR | Auto-fixes formatting/lint errors |
| `autofix:clean` | PR | Aggressive autofix with cosmetic repairs |
| `agent:codex` | Issue | Creates PR from issue |
| `agents:format` | Issue | Direct one-step formatting |
| `agents:optimize` | Issue | Analyze and suggest improvements |
| `agents:apply-suggestions` | Issue | Apply optimization suggestions |
| `agents:capability-check` | Issue | Check if agent can complete |
| `agents:dedup` | Issue | Check for duplicates |
| `agents:auto-label` | Issue | Apply appropriate labels |
| `agents:paused` | PR | Pause keepalive/agent work |
| `verify:checkbox` | PR (merged) | Verify checkboxes complete |
| `verify:evaluate` | PR (merged) | AI code review |
| `verify:compare` | PR (merged) | Multi-model comparison |
| `verify:create-issue` | PR (merged) | Create follow-up issue |

### Auto-Applied Labels (Status)

| Label | Meaning |
|-------|---------|
| `agents:formatted` | Issue has been formatted |
| `agents:keepalive` | Keepalive is monitoring this PR |
| `agent:needs-attention` | Human intervention required |
| `agents:auto-pilot-pause` | Auto-pilot paused |
| `agents:auto-pilot-failed` | Auto-pilot stopped due to errors |
| `agents:allow-change` | Permission signal for `agents-guard`; bypasses guard-level CODEOWNER approval only for dependency-only `uses:` reference updates from Dependabot/Renovate or repository owner/member/collaborator PRs. Workflows applies it to dependency-bot PRs through the label job in `maint-auto-lock-deps.yml`; arbitrary workflow logic edits still require review. |
| `needs-human` | Escalated to human |
| `follow-up` | Created as follow-up to another issue/PR |
| `duplicate` | Potential duplicate detected |

---

## Workflow Triggers Summary

### Issue Events

| Event | Workflows That Trigger |
|-------|----------------------|
| Issue opened | Auto-label, Duplicate detection, Issue intake |
| Label added: `agents:format` | Issue optimizer |
| Label added: `agents:optimize` | Issue optimizer |
| Label added: `agents:apply-suggestions` | Issue optimizer |
| Label added: `agent:codex` | Issue intake, Capability check |
| Label added: `agents:capability-check` | Capability checker |

### PR Events

| Event | Workflows That Trigger |
|-------|----------------------|
| PR opened | Gate (CI), Agents 80 PR Event Hub, Agents Guard |
| Label added: `autofix` | Autofix loop |
| Label added: `agents:keepalive` | Enables keepalive loop (runs on Gate workflow_run) |
| Label removed: `agents:paused` | Keepalive resumes |
| PR merged | Verifier (if verify labels present) |
| Label added: `verify:*` (after merge) | Verifier workflows |

### Continuous Monitoring

| Workflow | Runs |
|----------|------|
| Keepalive loop | Gate workflow_run for eligible PRs (and manual dispatch) |
| Bot comment handler | On every issue/PR comment |

---

## Complete Feature Reference

### Issue Formatting & Optimization

#### `agents:format` - Direct Format
**Quick, one-step formatting**

Immediately formats your issue to the standard template with sections:
- **Why**: Context and motivation
- **Scope**: What's included
- **Non-Goals**: What's excluded
- **Tasks**: Checklist of work items
- **Acceptance Criteria**: How to verify completion
- **Implementation Notes**: Technical guidance

**Use When:** Issue is already well-written but needs structure

**Result:** Label removed, `agents:formatted` added automatically

---

#### `agents:optimize` - Analyze & Suggest
**Two-step formatting with human review**

AI analyzes your issue and posts suggestions:
- Tasks that are too broad (should be split)
- Tasks the agent cannot complete (with reasons)
- Subjective acceptance criteria (with objective alternatives)
- Missing sections or formatting issues

**Use When:** Issue needs significant restructuring or you want expert feedback

**Next Step:** Review suggestions, then add `agents:apply-suggestions` to apply

---

#### `agents:apply-suggestions` - Apply Formatting
**Applies optimization suggestions**

Extracts suggestions from the analysis comment and:
- Reformats the issue body
- Moves blocked tasks to "Deferred Tasks" section
- Adds proper template structure
- Marks as `agents:formatted`

**Prerequisites:** Must have optimization suggestions comment from `agents:optimize`

---

### Agent Assignment & PR Creation

#### `agent:codex` - Create PR from Issue
**Assigns Codex agent to create a PR**

1. Creates branch `codex/issue-<number>`
2. Opens a ready-for-review PR linked to the issue
3. Agent begins implementing tasks
4. Keeps working through keepalive system
5. Keeps dependency and progress state in labels, checks, and the PR body

**Prerequisites:**
- Issue must be formatted (`agents:formatted` label)
- Valid agent assignee configured

**Monitoring:** Check PR for progress comments and commits

---

#### `agents:capability-check` - Pre-flight Check
**Checks if an agent can complete the issue**

Before assigning an agent, validates:
- All tasks are achievable by AI
- No external dependencies required
- Clear acceptance criteria exist
- No blocked/deferred tasks

**Use When:** Uncertain if an issue is suitable for automation

**Result:** Comment with ✅ proceed or ⚠️ concerns

---

### Duplicate Detection & Auto-Labeling

#### `agents:dedup` - Check for Duplicates
**Finds potential duplicate issues**

Searches for similar issues by:
- Title similarity
- Body content overlap
- Keyword matching

**Result:** If duplicate found, adds `duplicate` label and comment with link

**Threshold:** 92% similarity required to flag

---

#### `agents:auto-label` - Automatic Issue Labeling
**Applies appropriate labels based on content**

Analyzes issue text and applies:
- `bug` for error reports, crashes, incorrect behavior
- `enhancement` for feature requests, improvements
- `documentation` for docs updates

**Use When:** You want consistent labeling across issues

**Note:** Only applies the best-matching label (not multiple)

---

### PR Automation & Monitoring

#### `agents:keepalive` - Continue Agent Work
**Keeps agent working until PR is complete**

Monitors PR and:
- Dispatches agent for next task when ready
- Handles merge conflicts automatically
- Updates progress comments
- Pauses on CI failures
- Escalates to human if stuck

**Auto-added:** When agent creates PR

**Control:** Add `agents:paused` to pause

---

#### `autofix` - Automatic Code Fixes
**Fixes formatting and lint errors**

Runs repository's configured tools:
- Code formatters (black, prettier, etc.)
- Import organizers
- Linters with auto-fix
- Type annotation fixes

**Variants:**
- `autofix:clean` - More aggressive, includes cosmetic repairs
- `autofix:clean-only` - Only cosmetic changes
- `autofix:bot-comments` - Removes bot comment artifacts

**Use When:** CI is failing on style/format issues

---

#### `autofix:patch` - Emergency Fixes
**Applies fixes when push permissions unavailable**

If autofix can't push directly:
1. Creates a patch file
2. Uploads as artifact
3. Comments on PR with instructions

**Manual Step Required:** Download and apply patch

---

### Verification & Quality Assurance

#### `verify:checkbox` - Check Acceptance Criteria
**Verifies checkboxes are complete**

After PR merge, validates:
- All task checkboxes are checked
- Acceptance criteria boxes checked
- No incomplete items

**Result:** Comment on PR, optional follow-up issue

---

#### `verify:evaluate` - AI Code Review
**LLM evaluation of merged changes**

Runs AI review of the PR:
- Rates correctness, completeness, quality, testing
- Identifies concerns
- Scores each dimension (1-10)
- Suggests improvements

**Result:** Detailed evaluation comment

---

#### `verify:compare` - Multi-Model Comparison
**Compare across different AI models**

Runs verification with multiple models:
- Side-by-side comparison
- Consensus concerns
- Model-specific feedback

**Use When:** Want robust validation of complex changes

---

#### `verify:create-issue` - Create Follow-up from Verification
**Turns verification feedback into new issue**

Extracts concerns from verification comment:
- Low scores (<7/10)
- Specific concerns noted
- Creates structured follow-up issue
- Links back to original PR
- Auto-adds `agents:optimize` for formatting

**Use When:** Verification found issues that need work

---

### Advanced Automation

The [shared opener and closer](https://github.com/stranske/Workflows/blob/main/docs/ops/LOCAL_LANES.md#lanes-overview) own issue admission and guarded promotion.

---

## Troubleshooting

### Issue-format hold recovery procedures

When the issue optimizer detects more than three runs for the same issue in one
hour, it applies `agents:auto-pilot-pause` to stop the recursion.

1. Inspect the recent `agents-issue-optimizer.yml` runs and the issue body for
   repeated tasks, malformed sections, or a failing formatter.
2. Repair the issue body or the Workflows source that caused the repeated run.
3. Confirm that the issue is no longer being redispatched and that its body is
   valid before resuming automation.
4. Remove `agents:auto-pilot-pause` to allow the issue through the normal format
   and shared opener gates again.

Do not remove the pause label before correcting the cause; doing so can restart
the same recursion and exhaust the bounded retry cap again.

### Format-guard pause

When the issue format guard pauses an issue (its comment carries
`<!-- format-guard:attempt-cap -->`) after three real rewrite attempts or three
optimizer crashes, no human action is required: the opener lane (opener-core)
rewrites and re-validates paused issues automatically. Remove
`agents:auto-pilot-pause` only to force an earlier retry; the guard then starts
a fresh budget.

### Issue: Agent Not Starting

**Symptoms:** Added `agent:codex` but nothing happens

**Solutions:**
1. Check issue has `agents:formatted` label
   - If not, add `agents:format` or `agents:optimize`
2. Verify valid agent assignee exists
3. Check `agents:guard` workflow logs for errors
4. Look for `agent:needs-attention` label

---

### Issue: PR Keepalive Stuck

**Symptoms:** PR not progressing, agent not running

**Solutions:**
1. Check for `agents:paused` label - remove if present
2. Check CI status - must be green to continue
3. Look for merge conflicts - agent can auto-resolve
4. Check for `needs-human` - review PR for issues
5. Review keepalive summary comment for details

---

### Issue: Autofix Not Running

**Symptoms:** Added `autofix` label but no commits

**Solutions:**
1. PR must be open (not merged/closed)
2. PR must not be from a fork
3. PR must not be draft
4. Check `autofix.yml` workflow logs
5. Ensure CI has push permissions

---

### Issue: Verification Not Creating Follow-up

**Symptoms:** Added `verify:create-issue` but no issue created

**Solutions:**
1. PR must be merged
2. PR must have verification comment (from `verify:evaluate` or `verify:compare`)
3. Verification comment must contain concerns or low scores
4. Check `agents-80-pr-event-hub.yml` logs

---

### Issue has a legacy `agents:auto-pilot-failed` marker

Check the issue timeline and linked PR for an existing owner, then read the [shared opener](https://github.com/stranske/Workflows/blob/main/docs/ops/LOCAL_LANES.md#lanes-overview) disposition.

---

## Advanced Usage

### Combining Workflows

**Pattern 1: Careful Review Before Agent**
```
1. Add `agents:optimize` (get suggestions)
2. Review and edit suggestions comment if needed
3. Add `agents:apply-suggestions` (apply formatting)
4. Add `agents:capability-check` (verify agent can do it)
5. If ✅, add `agent:codex` (create PR)
```

**Pattern 2: Quick Format + Agent**
```
1. Add `agents:format` (quick formatting)
2. Add `agent:codex` (create PR)
```

**Pattern 3: Full Automation**
```
1. Submit an eligible issue through the shared opener lane
```

---

### Manual Keepalive Control

**To pause agent work temporarily:**
```
1. Add `agents:paused` label to PR
2. Make manual changes if needed
3. Remove `agents:paused` to resume
```

**To restart failed keepalive:**
```
1. Fix underlying issue (CI, conflicts, etc.)
2. Remove `agent:needs-attention` label
3. Keepalive resumes automatically
```

---

### Selective Verification

**Light verification:** Just check checkboxes
```
After merge, add: verify:checkbox
```

**Standard verification:** AI code review
```
After merge, add: verify:evaluate
```

**Thorough verification:** Multi-model review
```
After merge, add: verify:compare
```

**All verifications:**
```
Add all three labels before or after merge
```

---

### Breaking Down Complex Work

**For large features:**
```
1. Create a tracking issue with the full scope
2. Add `agents:optimize` or run Issue Optimizer with phase `analyze`
3. Review the Task splitting section of the optimizer comment
4. Apply approved suggestions with `agents:apply-suggestions`, edit Tasks directly, or create and link child issues manually
5. Add `agent:codex` to individual child issues when they are ready
```

**For stepwise development:**
```
1. Create issues for each logical step
2. Use "Depends on #<number>" in later issues
3. Complete issues in sequence
```

---

## Best Practices

### Writing Agent-Friendly Issues

✅ **Good:**
- Clear, specific tasks
- Objective acceptance criteria
- Concrete examples
- File/function names when known
- Expected behavior described

❌ **Avoid:**
- Vague requirements ("make it better")
- Subjective criteria ("looks good")
- External dependencies
- UI/UX decisions without examples
- "Research" or "investigate" tasks

---

### Choosing work for the shared opener

✅ **Good candidates:**
- Adding new API endpoint
- Writing tests for existing code
- Refactoring a module
- Fixing a specific bug
- Adding documentation

❌ **Not recommended:**
- Large architectural changes
- Multiple file refactors
- Complex debugging
- Performance optimization
- Security-sensitive changes

---

### Managing Verification Feedback

**When verification finds issues:**
1. Review verification comment
2. Decide if critical (needs immediate fix)
3. If critical: create manual follow-up issue
4. If minor: add `verify:create-issue` for auto-follow-up
5. Link follow-up to original PR

**Typical workflow:**
```
PR merged → Add verify:evaluate → Review results → 
If concerns → Add verify:create-issue → New issue auto-created
```

---

## Getting Help

**Resources:**
- [Full Documentation](https://github.com/stranske/Workflows/tree/main/docs)
- [Consumer Label Reference](https://github.com/stranske/Workflows/blob/main/templates/consumer-repo/docs/LABELS.md)
- [Agents Policy](https://github.com/stranske/Workflows/blob/main/docs/AGENTS_POLICY.md)

**For Issues:**
1. Check workflow logs in Actions tab
2. Look for bot comments on issue/PR
3. Search existing issues in Workflows repo
4. Create issue in Workflows repo with details

---

## Workflows Repository Maintenance

Workflows maintainers operate the shared jobs in the central repository. Use these references when a change affects your receiving repository.

<a name="sync--distribution"></a>
<a name="maint-68-sync-consumer-reposyml---sync-workflows-to-consumer-repos"></a>
<a name="maint-69-sync-integration-repoyml---sync-to-integration-test-repo"></a>
<a name="maint-71-merge-sync-prsyml---auto-merge-sync-prs"></a>
<a name="maint-62-integration-consumeryml---integration-testing"></a>
<a name="sync-manifest-management"></a>

### Consumer sync and manifest changes

Workflows owns the manifest and stages updates in consumer pull requests. Follow the canary and promotion procedure for the affected repositories. [Consumer maintenance and sync](https://github.com/stranske/Workflows/blob/main/docs/ops/CONSUMER_REPO_MAINTENANCE.md#sync-workflow-details).

<a name="version-management"></a>
<a name="maint-60-releaseyml---create-release"></a>
<a name="maint-52-sync-dev-versionsyml---sync-dev-versions"></a>
<a name="maint-sync-action-versionsyml---update-action-versions"></a>
<a name="dependency-management"></a>
<a name="renovate-dependency-and-lockfile-updates"></a>
<a name="maint-auto-update-pypi-versionsyml---auto-update-pypi-packages"></a>
<a name="dependency-pr-labels-and-lock-refresh"></a>
<a name="shared-development-tool-pins"></a>
<a name="maintenance-operations"></a>
<a name="maint-39-test-llm-providersyml---test-llm-providers"></a>
<a name="maint-45-cosmetic-repairyml---cosmetic-code-repairs"></a>
<a name="maint-46-post-ciyml---post-ci-cleanup"></a>
<a name="maint-47-disable-legacy-workflowsyml---disable-deprecated-workflows"></a>
<a name="review-registered-workflows-after-retirement"></a>
<a name="tool-version-freshness-report-central-only"></a>
<a name="maint-52-validate-workflowsyml---workflow-validation"></a>
<a name="label-guide-delivery-no-dedicated-workflow"></a>
<a name="maint-66-monthly-audityml---monthly-repository-audit"></a>
<a name="maint-71-auto-fix-integrationyml---auto-fix-integration-issues"></a>
<a name="maint-72-fix-pr-body-conflictsyml---fix-pr-body-conflicts"></a>
<a name="maint-coverage-guardyml---coverage-threshold-check"></a>

### Versions, dependencies and maintenance jobs

Check the central workflow catalog for the current job name and trigger. The integration guide explains how version selection works for reusable workflows and templates. [Workflow catalog](https://github.com/stranske/Workflows/blob/main/docs/ci/WORKFLOWS.md#autofix--maintenance). [Version selection](https://github.com/stranske/Workflows/blob/main/docs/INTEGRATION_GUIDE.md#versioning-strategy).

<a name="health--quality"></a>
<a name="health-40-repo-selfcheckyml---repository-self-check"></a>
<a name="health-42-actionlintyml---workflow-linting"></a>
<a name="ci-signature-fixtures-in-workflows"></a>
<a name="health-44-gate-branch-protectionyml---branch-protection-validation"></a>
<a name="health-50-security-scanyml---security-scanning"></a>
<a name="health-67-integration-sync-checkyml---integration-sync-status"></a>
<a name="health-70-validate-sync-manifestyml---sync-manifest-validation"></a>
<a name="health-codex-auth-checkyml---codex-authentication-test"></a>
<a name="health-keepalive-e2eyml---keepalive-end-to-end-test"></a>
<a name="health-41-repo-healthyml---comprehensive-health-check"></a>
<a name="workflow-monitoring--debugging"></a>
<a name="using-workflow-logs"></a>
<a name="testing-workflows-locally"></a>
<a name="manual-workflow-dispatch"></a>
<a name="troubleshooting-maintenance-workflows"></a>
<a name="sync-not-creating-prs"></a>
<a name="integration-tests-failing"></a>
<a name="auto-merge-not-working"></a>
<a name="dependabot-prs-not-auto-labeled"></a>

### Health checks and troubleshooting

Start with the affected run in the receiver’s Actions tab. For centrally managed checks, use the health inventory and the sync verification checklist. [Repository health checks](https://github.com/stranske/Workflows/blob/main/docs/ci/WORKFLOWS.md#repository-health-checks). [Sync verification checklist](https://github.com/stranske/Workflows/blob/main/docs/ops/CONSUMER_REPO_MAINTENANCE.md#verification-checklist).

<a name="maintenance-best-practices"></a>
<a name="before-syncing-to-consumer-repos"></a>
<a name="after-major-changes"></a>
<a name="regular-maintenance-schedule"></a>
<a name="emergency-rollback"></a>
<a name="required-secrets--configuration"></a>
<a name="repository-secrets-workflows-repo"></a>
<a name="repository-variables"></a>
<a name="contact--support"></a>

### Receiver setup and recovery

Use the setup guide for receiver permissions and secrets. To reverse a delivered change, use a reviewed revert through the owning repository and check its receiving head. [Integration and required setup](https://github.com/stranske/Workflows/blob/main/docs/INTEGRATION_GUIDE.md#required-setup).
