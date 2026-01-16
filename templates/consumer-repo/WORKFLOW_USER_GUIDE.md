# Workflow User Guide

**Version:** 1.0  
**Last Updated:** January 11, 2026  
**Source:** [Workflows Repository](https://github.com/stranske/Workflows)

This guide explains how to use the automated workflows in your repository. All workflows are managed by the central Workflows repository and synced automatically.

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
- Codex agent creates a branch and opens a draft PR
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

### 3. End-to-End Automation (Auto-Pilot)

**Use Case:** You want complete hands-off automation from issue to merged PR

**Steps:**
1. Create a well-structured issue with clear tasks
2. Add label: `agents:auto-pilot`
3. Monitor progress comments

**What Happens:**
1. ✅ Issue is formatted automatically
2. ✅ Issue is analyzed and optimized
3. ✅ Suggestions are applied
4. ✅ Agent creates PR
5. ✅ Keepalive monitors and continues work
6. ✅ PR is auto-merged when ready (if conditions met)
7. ✅ Verification runs post-merge

**Safety Limits:**
- Maximum 10 workflow cycles
- 4-hour timeout
- Pause anytime with `agents:auto-pilot-pause`
- Stops on errors with `agents:auto-pilot-failed`
- Escalates to `needs-human` on repeated failures

**Time:** 20 minutes to 2 hours depending on complexity

**Best For:** Well-scoped tasks like adding a new endpoint, refactoring a module, or adding tests

---

## Label Reference

### User-Applied Labels (Triggers)

| Label | Where | What It Does |
|-------|-------|--------------||
| `autofix` | PR | Auto-fixes formatting/lint errors |
| `autofix:clean` | PR | Aggressive autofix with cosmetic repairs |
| `agent:codex` | Issue | Creates PR from issue |
| `agents:format` | Issue | Direct one-step formatting |
| `agents:optimize` | Issue | Analyze and suggest improvements |
| `agents:apply-suggestions` | Issue | Apply optimization suggestions |
| `agents:auto-pilot` | Issue | Full end-to-end automation |
| `agents:capability-check` | Issue | Check if agent can complete |
| `agents:decompose` | Issue | Break into smaller issues |
| `agents:dedup` | Issue | Check for duplicates |
| `agents:auto-label` | Issue | Apply appropriate labels |
| `agents:paused` | PR | Pause keepalive/agent work |
| `verify:checkbox` | PR (merged) | Verify checkboxes complete |
| `verify:evaluate` | PR (merged) | AI code review |
| `verify:compare` | PR (merged) | Multi-model comparison |
| `verify:create-issue` | PR (merged) | Create follow-up issue |

### Auto-Applied Labels (Status)

| Label | Meaning |
|-------|---------||
| `agents:formatted` | Issue has been formatted |
| `agents:keepalive` | Keepalive is monitoring this PR |
| `agent:needs-attention` | Human intervention required |
| `agents:auto-pilot-pause` | Auto-pilot paused |
| `agents:auto-pilot-failed` | Auto-pilot stopped due to errors |
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
| Label added: `agents:decompose` | Task decomposer |
| Label added: `agents:capability-check` | Capability checker |
| Label added: `agents:auto-pilot` | Auto-pilot orchestrator |

### PR Events

| Event | Workflows That Trigger |
|-------|----------------------|
| PR opened | Gate (CI), PR Meta, Agents Guard |
| Label added: `autofix` | Autofix loop |
| Label added: `agents:keepalive` | Enables keepalive loop (runs on Gate workflow_run) |
| Label removed: `agents:paused` | Keepalive resumes |
| PR merged | Verifier (if verify labels present) |
| Label added: `verify:*` (after merge) | Verifier workflows |

### Continuous Monitoring

| Workflow | Runs |
|----------|------|
| Keepalive loop | Gate workflow_run for eligible PRs (and manual dispatch) |
| Auto-pilot | On label changes for active issues |
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
2. Opens draft PR linked to issue
3. Agent begins implementing tasks
4. Keeps working through keepalive system
5. Marks PR ready when complete

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

#### `agents:decompose` - Break Down Large Issues
**Splits complex issues into smaller sub-issues**

For issues with >5 tasks or large scope:
1. Analyzes tasks and dependencies
2. Creates multiple smaller issues
3. Links them together
4. Each sub-issue is agent-ready

**Use When:** Issue feels too large for one PR

**Result:** Original issue gets sub-task links, new issues created

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

#### `agents:auto-pilot` - Full End-to-End
**Complete automation from issue to merge**

Orchestrates entire pipeline:
1. Format → 2. Optimize → 3. Apply → 4. Agent → 5. Keepalive → 6. Merge → 7. Verify

**Safety:**
- Max 10 cycles
- 4-hour timeout
- Pause: `agents:auto-pilot-pause`
- Failure: `agents:auto-pilot-failed`

**Best For:** Well-defined, medium complexity tasks

---

## Troubleshooting

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
4. Check `agents-verify-to-issue.yml` logs

---

### Issue: Auto-Pilot Stopped Early

**Symptoms:** `agents:auto-pilot-failed` label added

**Possible Causes:**
1. Exceeded 10 cycle limit - issue too complex
2. Hit 4-hour timeout - issue taking too long
3. Repeated failures - agent stuck on same task
4. CI repeatedly failing - infrastructure issue

**Next Steps:**
1. Review progress comments on issue
2. Check last PR attempt for errors
3. Simplify issue scope if too complex
4. Remove failed label and retry with `agents:paused` for manual control

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
1. Add `agents:auto-pilot` (handles everything)
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
1. Create meta-issue with full scope
2. Add `agents:decompose` label
3. Review created sub-issues
4. Add `agent:codex` to each sub-issue individually
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

### When to Use Auto-Pilot

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
- [Label Reference](https://github.com/stranske/Workflows/blob/main/docs/LABELS.md)
- [Agents Policy](https://github.com/stranske/Workflows/blob/main/docs/AGENTS_POLICY.md)

**For Issues:**
1. Check workflow logs in Actions tab
2. Look for bot comments on issue/PR
3. Search existing issues in Workflows repo
4. Create issue in Workflows repo with details

---

# Workflows Repository Maintenance

*This section is for maintainers of the Workflows repository and consumer repo administrators.*

The Workflows repository includes maintenance workflows that handle sync, updates, health checks, and repo management. These run from the Workflows repository itself and require appropriate permissions.

---

## Sync & Distribution

### `maint-68-sync-consumer-repos.yml` - Sync Workflows to Consumer Repos
**Purpose:** Pushes workflow updates from template to all consumer repos

**Trigger:** Manual dispatch or on push to main

**What It Does:**
1. Reads `config/sync-manifest.json` for file list
2. For each consumer repo:
   - Creates branch `sync/workflows-update`
   - Copies files from `templates/consumer-repo/`
   - Opens PR with changes
3. Assigns reviewers and labels

**Use When:** New workflow version ready to deploy

**Files Synced:** All files listed in sync manifest (workflows, docs, configs)

---

### `maint-69-sync-integration-repo.yml` - Sync to Integration Test Repo
**Purpose:** Deploys workflows to integration test repo for E2E testing

**Trigger:** Manual dispatch or scheduled (nightly)

**What It Does:**
- Syncs workflows to dedicated integration repo
- Creates test issues and PRs
- Validates workflow execution
- Reports test results

**Use When:** Before production sync, after major changes

---

### `maint-71-merge-sync-prs.yml` - Auto-Merge Sync PRs
**Purpose:** Automatically merges sync PRs after validation

**Trigger:** On sync PR status checks completion

**Conditions:**
- All status checks pass
- No merge conflicts
- Labeled `automation` and `workflows-sync`
- Approved or auto-approved

**Safety:** Only merges if CI fully green

---

### `maint-62-integration-consumer.yml` - Integration Testing
**Purpose:** Runs end-to-end tests in integration environment

**Trigger:** After sync to integration repo

**Tests:**
- Agent creation flows
- Keepalive loops
- Autofix operations
- Verification workflows
- Label automation

**Use When:** Validating new features before production

---

## Version Management

### `maint-60-release.yml` - Create Release
**Purpose:** Creates GitHub release with version tag

**Trigger:** Manual dispatch with version number

**What It Does:**
1. Validates semantic version format (v1.2.3)
2. Creates git tag
3. Generates release notes from PRs
4. Publishes GitHub release
5. Triggers changelog update

**Use When:** Ready to cut new version

**Input:** Version number (e.g., `v1.5.0`)

---

### `maint-61-create-floating-v1-tag.yml` - Update Floating Tag
**Purpose:** Updates `v1` tag to latest `v1.x.x` release

**Trigger:** After new release created

**What It Does:**
- Finds latest v1 series release
- Updates `v1` tag to point to it
- Enables consumers to use `@v1` for latest

**Use When:** After any v1.x.x release

---

### `maint-52-sync-dev-versions.yml` - Sync Dev Versions
**Purpose:** Updates development environment versions

**Trigger:** On push to main or manual

**What It Does:**
- Syncs Python version from `.python-version`
- Updates Node.js version in workflows
- Updates action versions in workflows
- Commits version bumps

**Use When:** After dependency updates

---

### `maint-sync-action-versions.yml` - Update Action Versions
**Purpose:** Updates GitHub Action versions in workflows

**Trigger:** Weekly scheduled or manual

**What It Does:**
1. Scans all workflow files
2. Finds action usages (e.g., `actions/checkout@v3`)
3. Checks for latest versions
4. Updates to newest stable versions
5. Opens PR with updates

**Use When:** Keeping actions up to date

---

## Dependency Management

### `maint-51-dependency-refresh.yml` - Refresh Dependencies
**Purpose:** Updates Python dependencies to latest compatible versions

**Trigger:** Weekly scheduled or manual

**What It Does:**
1. Runs `pip list --outdated`
2. Updates `pyproject.toml` with new versions
3. Regenerates `requirements.txt`
4. Runs tests
5. Opens PR if changes

**Use When:** Regular maintenance or after security advisories

---

### `maint-auto-update-pypi-versions.yml` - Auto-Update PyPI Packages
**Purpose:** Automatically updates Python package versions

**Trigger:** Daily scheduled

**What It Does:**
- Checks PyPI for latest versions
- Updates minor/patch versions automatically
- Creates PR for major version updates
- Runs CI to validate

**Safety:** Only auto-merges patch versions

---

### `maint-dependabot-auto-label.yml` - Label Dependabot PRs
**Purpose:** Auto-labels Dependabot PRs by category

**Trigger:** When Dependabot opens PR

**Labels Applied:**
- `dependencies` (all)
- `python` for Python packages
- `github-actions` for action updates
- `security` for security updates

**Use When:** Automatic, no action needed

---

### `maint-dependabot-auto-lock.yml` - Lock Dependabot PRs
**Purpose:** Prevents auto-merge for major version updates

**Trigger:** When Dependabot PR is major version

**What It Does:**
- Detects major version bumps
- Adds `do-not-merge` label
- Comments with review request
- Requires manual review

**Use When:** Automatic protection

---

### `maint-sync-env-from-pyproject.yml` - Sync Environment Files
**Purpose:** Keeps environment configs in sync with `pyproject.toml`

**Trigger:** When `pyproject.toml` changes

**What It Does:**
- Generates `requirements.txt`
- Updates `.python-version`
- Syncs dev dependencies
- Commits synchronized files

**Use When:** After editing `pyproject.toml`

---

## Health & Quality

### `health-40-repo-selfcheck.yml` - Repository Self-Check
**Purpose:** Validates repository health and configuration

**Trigger:** Daily scheduled or manual

**Checks:**
- All required files present
- Workflow syntax valid
- Labels configured correctly
- Branch protection active
- Required secrets exist
- Documentation up to date

**Result:** Issue created if problems found

---

### `health-41-repo-health.yml` - Comprehensive Health Check
**Purpose:** Deep health assessment of repository

**Trigger:** Weekly scheduled

**Checks:**
- Stale issues/PRs
- Unused labels
- Deprecated workflows
- Security vulnerabilities
- Outdated dependencies
- Missing documentation

**Result:** Health report issue with action items

---

### `health-42-actionlint.yml` - Workflow Linting
**Purpose:** Validates workflow YAML syntax and best practices

**Trigger:** On workflow file changes

**What It Does:**
- Runs `actionlint` on all workflow files
- Checks for syntax errors
- Validates action versions exist
- Checks for common mistakes
- Reports errors in PR

**Use When:** Automatic on PR, also available manually

---

### `health-43-ci-signature-guard.yml` - CI Integrity Check
**Purpose:** Ensures CI workflows haven't been tampered with

**Trigger:** On CI workflow changes

**What It Does:**
- Computes checksums of CI workflows
- Compares against known good signatures
- Blocks PRs with unauthorized changes
- Requires maintainer review

**Security:** Prevents malicious CI modifications

---

### `health-44-gate-branch-protection.yml` - Branch Protection Validation
**Purpose:** Verifies branch protection rules are active

**Trigger:** Daily check

**Validates:**
- Main branch protected
- Required status checks configured
- Code review required
- Dismiss stale reviews enabled
- Force push disabled

**Result:** Alert if protection weakened

---

### `health-50-security-scan.yml` - Security Scanning
**Purpose:** Scans for security vulnerabilities

**Trigger:** Weekly scheduled and on push

**Scans:**
- Dependency vulnerabilities (GitHub Advisory)
- Code security issues (CodeQL)
- Secret leaks
- Known CVEs in dependencies

**Result:** Security report and alerts

---

### `health-67-integration-sync-check.yml` - Integration Sync Status
**Purpose:** Verifies integration repo is in sync

**Trigger:** After sync operations

**Checks:**
- Workflow files match source
- Versions are current
- No drift from template
- Integration tests passing

**Result:** Warning if out of sync

---

### `health-70-validate-sync-manifest.yml` - Sync Manifest Validation
**Purpose:** Ensures sync manifest is correct

**Trigger:** On manifest changes

**Validates:**
- All listed files exist
- File paths are valid
- No duplicate entries
- Required files included
- Manifest JSON is valid

**Result:** Blocks PR if invalid

---

### `health-codex-auth-check.yml` - Codex Authentication Test
**Purpose:** Validates Codex API credentials

**Trigger:** Daily scheduled

**Tests:**
- API key valid
- Authentication successful
- Rate limits okay
- Model access available

**Result:** Alert if auth fails

---

### `health-keepalive-e2e.yml` - Keepalive End-to-End Test
**Purpose:** Tests keepalive system with real scenario

**Trigger:** Weekly scheduled

**Test Steps:**
1. Create test issue
2. Assign agent
3. Monitor keepalive operation
4. Verify progression
5. Cleanup test artifacts

**Result:** Report on keepalive health

---

## Maintenance Operations

### `maint-39-test-llm-providers.yml` - Test LLM Providers
**Purpose:** Validates all LLM API integrations

**Trigger:** Daily scheduled or manual

**Tests:**
- OpenAI API
- Anthropic API
- Google AI API
- Azure OpenAI
- Other configured providers

**Checks:**
- API keys valid
- Models accessible
- Rate limits okay
- Response quality

**Result:** Status report with any issues

---

### `maint-45-cosmetic-repair.yml` - Cosmetic Code Repairs
**Purpose:** Fixes cosmetic code issues across repo

**Trigger:** Manual dispatch

**Fixes:**
- Trailing whitespace
- Missing final newlines
- Inconsistent line endings
- Spacing around operators
- Import organization

**Use When:** Spring cleaning or before release

---

### `maint-46-post-ci.yml` - Post-CI Cleanup
**Purpose:** Cleanup tasks after CI runs

**Trigger:** After CI completion

**Tasks:**
- Archive test artifacts
- Clean build directories
- Update coverage reports
- Post status comments
- Upload logs

**Use When:** Automatic

---

### `maint-47-disable-legacy-workflows.yml` - Disable Deprecated Workflows
**Purpose:** Disables old workflow versions

**Trigger:** Manual dispatch with workflow name

**What It Does:**
- Renames workflow file (adds `.disabled`)
- Updates documentation
- Posts deprecation notice
- Schedules for removal

**Use When:** Replacing old workflow with new version

---

### `maint-50-tool-version-check.yml` - Tool Version Audit
**Purpose:** Checks versions of all development tools

**Trigger:** Weekly scheduled

**Checks:**
- Python version
- Node.js version
- pip version
- git version
- gh version
- docker version
- Action versions

**Result:** Report on outdated tools

---

### `maint-52-validate-workflows.yml` - Workflow Validation
**Purpose:** Comprehensive workflow validation

**Trigger:** On workflow changes or manual

**Validates:**
- YAML syntax
- Schema compliance
- Action versions valid
- Secrets referenced correctly
- Permissions appropriate
- Trigger events valid

**Result:** Validation report

---

### `maint-65-sync-label-docs.yml` - Sync Label Documentation
**Purpose:** Keeps label docs in sync with actual labels

**Trigger:** On label changes or manual

**What It Does:**
1. Fetches current labels from repos
2. Updates `docs/LABELS.md`
3. Adds descriptions for new labels
4. Marks deprecated labels
5. Commits documentation

**Use When:** After adding/removing labels

---

### `maint-66-monthly-audit.yml` - Monthly Repository Audit
**Purpose:** Comprehensive monthly review

**Trigger:** First of each month

**Audits:**
- All workflows functioning
- No orphaned branches
- Issues/PRs properly labeled
- Documentation current
- Dependency security
- Access controls
- Backup status

**Result:** Detailed audit report issue

---

### `maint-70-fix-integration-formatting.yml` - Fix Integration Repo Formatting
**Purpose:** Auto-fixes formatting in integration repo

**Trigger:** After integration sync

**What It Does:**
- Runs formatters on integration repo
- Fixes common lint issues
- Commits fixes
- Ensures clean state for testing

**Use When:** Automatic after sync

---

### `maint-71-auto-fix-integration.yml` - Auto-Fix Integration Issues
**Purpose:** Applies autofixes to integration repo

**Trigger:** After integration CI fails

**What It Does:**
- Identifies fixable issues
- Applies automatic corrections
- Re-runs CI
- Reports remaining issues

**Use When:** Integration CI has auto-fixable errors

---

### `maint-72-fix-pr-body-conflicts.yml` - Fix PR Body Conflicts
**Purpose:** Resolves conflicts in PR descriptions

**Trigger:** When PR body has merge conflict markers

**What It Does:**
- Detects conflict markers in PR body
- Resolves using recent version
- Updates PR description
- Comments with resolution

**Use When:** Sync PRs with conflicting descriptions

---

### `maint-coverage-guard.yml` - Coverage Threshold Check
**Purpose:** Enforces code coverage requirements

**Trigger:** On PR or manual

**Checks:**
- Overall coverage meets threshold (80%)
- No file below minimum (60%)
- Coverage not decreased
- All critical paths covered

**Result:** Blocks merge if coverage drops

---

## Workflow Monitoring & Debugging

### Using Workflow Logs

**To debug workflow issues:**
1. Go to Actions tab in repository
2. Select failed workflow run
3. Click on failed job
4. Expand step that failed
5. Review error messages and logs

**Common Issues:**
- **Permission errors:** Check repository secrets
- **API rate limits:** Wait for limit reset
- **Syntax errors:** Run actionlint locally
- **Missing files:** Verify sync manifest

---

### Testing Workflows Locally

**For workflow development:**

```bash
# Install act (local GitHub Actions runner)
brew install act  # or: curl ... | bash

# Run workflow locally
act -j <job-name> -s GITHUB_TOKEN=<token>

# Dry run to see what would execute
act -n
```

**Limitations:** Some GitHub-specific features won't work locally

---

### Manual Workflow Dispatch

**To trigger manually:**
1. Go to Actions tab
2. Select workflow on left
3. Click "Run workflow" dropdown
4. Fill in any required inputs
5. Click "Run workflow"

**Available Inputs:** See workflow file `workflow_dispatch` section

---

## Maintenance Best Practices

### Before Syncing to Consumer Repos

✅ **Checklist:**
1. All CI checks passing on main
2. Integration tests pass
3. Documentation updated
4. CHANGELOG.md updated
5. Version bumped (if applicable)
6. Reviewed by second maintainer
7. Tested on integration repo

---

### After Major Changes

**Recommended sequence:**
1. Merge to main
2. Run integration sync
3. Monitor integration tests (24 hours)
4. Create release (if stable)
5. Sync to 1-2 test consumer repos
6. Monitor for issues (48 hours)
7. Sync to all consumer repos
8. Post announcement

---

### Regular Maintenance Schedule

**Daily:**
- Review failed workflows
- Check security alerts
- Monitor integration health

**Weekly:**
- Review open PRs
- Check dependency updates
- Run health checks
- Review audit results

**Monthly:**
- Full repository audit
- Label cleanup
- Documentation review
- Version planning
- Consumer repo sync

---

### Emergency Rollback

**If sync causes breaking issues:**

```bash
# In consumer repo:
git checkout <previous-working-commit>
git push -f origin main  # If really necessary

# Better: Revert specific files
git checkout <commit> .github/workflows/<broken-file>.yml
git commit -m "Revert workflow to stable version"
git push
```

**Then fix in Workflows repo and re-sync**

---

## Sync Manifest Management

The sync manifest (`config/sync-manifest.json`) controls what gets synced:

```json
{
  "files": [
    {
      "source": "templates/consumer-repo/.github/workflows/agents-auto-pilot.yml",
      "dest": ".github/workflows/agents-auto-pilot.yml"
    },
    {
      "source": "templates/consumer-repo/WORKFLOW_USER_GUIDE.md",
      "dest": "docs/WORKFLOW_USER_GUIDE.md"
    }
  ]
}
```

**To add new file to sync:**
1. Add entry to manifest
2. Validate with `health-70-validate-sync-manifest`
3. Test sync to integration repo
4. Sync to consumer repos

**To remove file:**
1. Remove from manifest
2. Sync will not delete (manual cleanup needed)
3. Document removal in CHANGELOG

---

## Required Secrets & Configuration

### Repository Secrets (Workflows Repo)

| Secret | Purpose | Used By |
|--------|---------|---------|
| `CODESPACES_WORKFLOWS` | High-privilege PAT for sync operations | Sync workflows |
| `OPENAI_API_KEY` | OpenAI API access | Agent workflows |
| `ANTHROPIC_API_KEY` | Anthropic API access | Agent workflows |
| `GH_APP_PRIVATE_KEY` | GitHub App authentication | Integration workflows |

### Repository Variables

| Variable | Value | Purpose |
|----------|-------|---------|
| `INTEGRATION_REPO` | `stranske/integration-test` | Integration testing target |
| `CONSUMER_REPOS` | JSON array | List of consumer repos for sync |
| `SYNC_ENABLED` | `true`/`false` | Enable/disable auto-sync |

---

## Troubleshooting Maintenance Workflows

### Sync Not Creating PRs

**Check:**
1. `CODESPACES_WORKFLOWS` token valid and has repo permissions
2. Consumer repo exists and accessible
3. Sync manifest valid (run validation workflow)
4. No existing open sync PR (closes old ones first)

---

### Integration Tests Failing

**Check:**
1. Integration repo has same secrets as consumer repos
2. Workflows synced correctly (no file permission issues)
3. Integration repo clean (no stale test artifacts)
4. API rate limits not exceeded

---

### Auto-Merge Not Working

**Check:**
1. Required status checks all green
2. PR has correct labels (`automation`, `workflows-sync`)
3. No merge conflicts
4. Branch protection rules allow auto-merge
5. Actor has merge permissions

---

### Dependabot PRs Not Auto-Labeled

**Check:**
1. PR opened by `dependabot[bot]`
2. Workflow has `pull_request: [opened]` trigger
3. Workflow has write permissions on PRs
4. Label exists in repository

---

## Contact & Support

**For workflow issues:**
- Create issue in Workflows repository
- Tag with `maintenance` and `bug`
- Include workflow name and run ID

**For sync issues:**
- Check integration test results first
- Review sync PR in consumer repo
- Check diff for unexpected changes

**For access/permissions:**
- Contact repository administrator
- Verify in repository settings > Collaborators

---

**Version History:**
- 1.0 (January 11, 2026): Initial comprehensive guide

**Maintained by:** [Workflows Repository](https://github.com/stranske/Workflows)
