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

*Last updated: December 25, 2025*
*Source of truth: Workflows repository*
