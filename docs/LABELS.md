# Label Reference Guide

This document describes all labels that trigger automated workflows or affect CI/CD behavior in repositories using the Workflows system.

## Quick Reference

| Label | Trigger | Effect |
|-------|---------|--------|
| `autofix` | PR labeled | Triggers automated code fixes |
| `autofix:clean` | PR labeled | Triggers clean-mode autofix (more aggressive) |
| `agent:codex` | Issue labeled | Triggers Codex agent assignment |
| `agent:codex-invite` | Issue labeled | Invites Codex agent to participate |
| `agent:needs-attention` | Auto-applied | Indicates agent needs human intervention |
| `status:ready` | Issue labeled | Marks issue as ready for agent processing |
| `agents:format` | Issue labeled | Direct issue formatting |
| `agents:formatted` | Auto-applied | Indicates issue has been formatted |
| `agents:optimize` | Issue labeled | Analyzes issue and posts suggestions |
| `agents:apply-suggestions` | Issue labeled | Applies optimization suggestions |
| `agents:paused` | PR labeled | Pauses keepalive loop on PR |
| `agents:keepalive` | PR labeled | Enables keepalive loop on PR |
| `verify:checkbox` | PR labeled | Runs verifier checkbox mode after merge |
| `verify:evaluate` | PR labeled | Runs verifier evaluation mode after merge |
| `verify:compare` | PR labeled | Runs verifier comparison mode after merge |
| `verify:create-issue` | PR labeled | Creates follow-up issue from verification |
| `verify:create-new-pr` | PR labeled | Creates follow-up issue and PR from verification |

---

## Autofix Labels

### `autofix`

**Applies to:** Pull Requests

**Trigger:** When applied to an open, non-draft PR

**Effect:** Initiates the CI Autofix Loop which:
1. Runs linting and formatting checks
2. Automatically commits fixes for:
   - Code formatting using the repository's configured formatters
   - Import organization
   - Trailing whitespace
   - Type annotation fixes (mypy suggestions)
3. Posts a summary comment on the PR

**Prerequisites:**
- PR must be from the same repository (not a fork)
- PR must not be in draft state
- PR must be open

**Workflow:** `autofix.yml` (CI Autofix Loop)

---

### `autofix:clean`

**Applies to:** Pull Requests

**Trigger:** When applied to an open, non-draft PR

**Effect:** Triggers a more aggressive "clean" mode autofix that:
1. Performs all standard autofix operations
2. Additionally runs cosmetic repairs
3. May reorganize imports more aggressively

**Note:** This label provides a stronger fix that might make more changes than the standard `autofix` label.

**Workflow:** `autofix.yml` (CI Autofix Loop)

---

## Agent Labels

### `agent:codex`

**Applies to:** Issues

**Trigger:** When applied to an issue

**Effect:** 
1. Activates the Codex agent assignment workflow
2. Validates that a valid agent assignee is present
3. If validated, enables automated code generation for the issue
4. Creates a `codex/issue-<number>` branch for agent work
5. Opens a draft PR linked to the issue

**Prerequisites:**
- Issue must have a valid agent assignee (configured in repository settings)
- Issue should have clear requirements in the description

**Workflow:** `agents-63-issue-intake.yml` (Agents 63 Issue Intake)

---

### `agent:codex-invite`

**Applies to:** Issues

**Trigger:** When applied to an issue that already has `agent:codex`

**Effect:**
1. Sends an invitation for the Codex agent to participate
2. Requires the base `agent:codex` label to be present

**Prerequisites:**
- Issue must already have `agent:codex` label
- Issue must have valid agent assignee

**Note:** Adding this label without `agent:codex` will result in an error.

**Workflow:** `agents-63-issue-intake.yml` (Agents 63 Issue Intake)

---

### `agent:needs-attention`

**Applies to:** Issues and Pull Requests

**Trigger:** Automatically applied by workflows

**Effect:**
1. Signals that human intervention is required
2. Agent processing is paused until addressed
3. Typically applied when:
   - Agent encounters an error
   - CI checks fail repeatedly
   - Agent requests clarification

**Action Required:** Review the issue/PR, address concerns, and remove the label to resume agent processing.

**Workflow:** Multiple workflows may apply this label

---

### `status:ready`

**Applies to:** Issues

**Trigger:** When applied to an issue with agent labels

**Effect:**
1. Marks the issue as ready for agent processing
2. Used in conjunction with `agent:codex` to signal readiness
3. May trigger the next step in the agent automation pipeline

**Workflow:** `agents-70-orchestrator.yml` (Agents 70 Orchestrator)

---

## Issue Formatting Labels (LangChain Enhancement)

These labels control the LangChain-powered issue formatting pipeline introduced in #484.

### `agents:format`

**Applies to:** Issues

**Trigger:** When applied to an issue

**Effect:**
1. Automatically formats the raw issue body into the AGENT_ISSUE_TEMPLATE structure
2. Uses LLM (GitHub Models API) with fallback to regex-based formatting
3. Adds proper sections: Why, Scope, Non-Goals, Tasks, Acceptance Criteria, Implementation Notes
4. Converts task items to checkboxes
5. Replaces the issue body with formatted version
6. Removes `agents:format` label and adds `agents:formatted`

**Use Case:** Quick, one-step formatting without review. Best for issues that are already well-structured but need template compliance.

**Workflow:** `agents-issue-optimizer.yml`

---

### `agents:formatted`

**Applies to:** Issues

**Trigger:** Automatically applied after formatting completes

**Effect:**
1. Indicates the issue has been formatted to AGENT_ISSUE_TEMPLATE
2. Signals the issue is ready for agent processing
3. Prevents re-formatting (workflows skip issues with this label)

**Note:** This is a result label, not a trigger label. Do not apply manually.

**Workflow:** Applied by `agents-issue-optimizer.yml`

---

### `agents:optimize`

**Applies to:** Issues

**Trigger:** When applied to an issue

**Effect:**
1. Analyzes the issue for agent compatibility and formatting quality
2. Posts a comment with suggestions including:
   - Tasks that are too broad (should be split)
   - Tasks the agent cannot complete (with reasons)
   - Subjective acceptance criteria (with objective alternatives)
   - Missing sections or formatting issues
3. Includes embedded JSON with structured suggestions
4. Prompts user to add `agents:apply-suggestions` to apply changes

**Use Case:** Two-step formatting with human review. Best for issues needing significant restructuring.

**Workflow:** `agents-issue-optimizer.yml`

---

### `agents:apply-suggestions`

**Applies to:** Issues

**Trigger:** When applied to an issue that has received optimization suggestions

**Prerequisites:**
- Issue must have a comment with optimization suggestions (from `agents:optimize`)
- The suggestions comment must contain valid JSON in `<!-- suggestions-json: -->` marker

**Effect:**
1. Extracts approved suggestions from the analysis comment
2. Applies all suggestions to reformat the issue body
3. Moves blocked tasks to "## Deferred Tasks (Requires Human)" section
4. Removes both `agents:optimize` and `agents:apply-suggestions` labels
5. Adds `agents:formatted` label

**Workflow:** `agents-issue-optimizer.yml`

---

## Verifier Labels

These labels trigger the post-merge verifier workflow on a merged PR.

### `verify:checkbox`

**Applies to:** Pull Requests

**Trigger:** When applied to a merged PR

**Effect:** Verifies acceptance criteria checkbox completion and opens follow-up issues if gaps are detected.

**Workflow:** `agents-verifier.yml`

---

### `verify:evaluate`

**Applies to:** Pull Requests

**Trigger:** When applied to a merged PR

**Effect:** Runs an LLM evaluation of the work and posts a report with optional follow-up issues.

**Workflow:** `agents-verifier.yml`

---

### `verify:compare`

**Applies to:** Pull Requests

**Trigger:** When applied to a merged PR

**Effect:** Runs the verifier across multiple models and posts a comparison report.

**Workflow:** `agents-verifier.yml`

---

### `verify:create-issue`

**Applies to:** Pull Requests

**Trigger:** When applied to a merged PR that has verification feedback

**Prerequisites:**
- PR must be merged
- PR must have a verification comment (from `verify:evaluate` or `verify:compare`)

**Effect:**
1. Extracts concerns and low scores from verification feedback
2. Creates a new follow-up issue with:
   - Link to original PR
   - Extracted concerns from verification
   - Scores below 7/10
   - Suggested tasks for addressing issues
3. Posts comment on original PR linking to new issue
4. Removes the `verify:create-issue` label after completion
5. Adds `agents:optimize` label to new issue for agent formatting

**Use Case:** User-triggered creation of follow-up work from verification feedback. Replaces automatic issue creation which was too aggressive.

**Workflow:** `agents-verify-to-issue.yml`

---

### `verify:create-new-pr`

**Applies to:** Pull Requests

**Trigger:** When applied to a merged PR that has verification feedback

**Prerequisites:**
- PR must be merged
- PR must already have verification context (for example from `verify:evaluate` or `verify:compare`)

**Effect:**
1. Creates a follow-up issue from verification concerns
2. Creates and bootstraps a follow-up PR for that issue
3. Removes `verify:create-new-pr` label after processing

**Workflow:** `agents-verify-to-new-pr.yml`

---

## Keepalive Control Labels

### `agents:paused`

**Applies to:** Pull Requests

**Trigger:** When applied to a PR with active keepalive

**Effect:**
1. Pauses all keepalive activity on the PR
2. Agent will not be dispatched until label is removed
3. Useful for manual intervention or debugging

**To Resume:** Remove the `agents:paused` label.

**Workflow:** `agents-keepalive-loop.yml`

---

### `agents:keepalive`

**Applies to:** Pull Requests

**Trigger:** When applied to a PR

**Effect:**
1. Enables the keepalive loop for the PR
2. Agent continues working until all tasks are complete
3. Tracks progress and updates PR status

**Prerequisites:**
- PR must have an `agent:*` label
- Gate workflow must pass

**Workflow:** `agents-keepalive-loop.yml`

---

## Informational Labels

These labels are used for categorization but do not trigger workflows.

### `follow-up`

**Applies to:** Issues

**Effect:** Indicates this issue was created as follow-up to another issue or PR.

**Applied by:** `agents-verify-to-issue.yml` workflow

---

### `needs-formatting`

**Applies to:** Issues  

**Effect:** Indicates the issue needs formatting to AGENT_ISSUE_TEMPLATE structure.

**Applied by:** Issue lint workflow (when enabled)

---

## CI/Build Labels

### `skip-ci` (if configured)

**Applies to:** Pull Requests

**Effect:** Some workflows may skip when this label is present. Check individual workflow configurations.

---

## Label Interaction Matrix

| Existing Label | New Label Added | Result |
|---------------|-----------------|--------|
| (none) | `autofix` | Triggers autofix |
| `autofix` | `autofix:clean` | May trigger clean mode |
| (none) | `agent:codex` | Triggers agent assignment |
| `agent:codex` | `agent:codex-invite` | Sends agent invitation |
| `agent:codex` | `status:ready` | Agent begins processing |
| `agent:needs-attention` | (removed) | Agent resumes processing |
| (none) | `agents:format` | Direct formatting |
| (none) | `agents:optimize` | Analyzes and posts suggestions |
| `agents:optimize` | `agents:apply-suggestions` | Applies suggestions, adds `agents:formatted` |
| `agents:formatted` | `agent:codex` | Issue ready for agent processing |

---

## Troubleshooting

### Autofix not running

1. Check that the PR is not a draft
2. Verify the PR is from the same repository (not a fork)
3. Check the Actions tab for any failed workflow runs

### Agent not processing issue

1. Verify `agent:codex` label is present
2. Check that a valid agent assignee is assigned
3. Look for `agent:needs-attention` label
4. Review the workflow run logs in the Actions tab

### Label applied but nothing happened

1. Labels only trigger on the `labeled` event - re-applying won't re-trigger
2. Remove and re-add the label to trigger again
3. Check workflow permissions in repository settings

---

## For Repository Administrators

### Configuring Agent Assignees

Valid agent assignees are configured per-repository. Contact your repository administrator to:
1. Add new agent assignees
2. Modify agent permissions
3. Configure agent environments

### Adding New Label Triggers

To add new label-triggered functionality:
1. Update the relevant workflow file
2. Add the label to this documentation
3. Sync documentation to consumer repositories

---

*Last updated: January 5, 2026*
*Source of truth: Workflows repository*
