# Keepalive Troubleshooting Guide

This document captures lessons learned from implementing keepalive functionality in consumer repositories, based on the Travel-Plan-Permission repo implementation (PRs #47-#94, December 2025).

## Overview

The keepalive system enables automated agent (Codex) continuation on pull requests. When a human posts `@codex <instructions>`, the system:
1. Detects the comment via `agents-pr-meta.yml`
2. Waits for Gate CI to pass
3. Dispatches the orchestrator to continue agent work
4. Repeats until all tasks are complete

## Critical Components

### Required Workflows (in consumer repo)

| Workflow | Purpose | Key Triggers |
|----------|---------|--------------|
| `agents-pr-meta.yml` | Detects keepalive comments, dispatches orchestrator | `issue_comment`, `pull_request`, `workflow_run` |
| `agents-70-orchestrator.yml` | Scheduled keepalive sweeps | `schedule`, `workflow_dispatch` |
| `agents-63-issue-intake.yml` | Creates issues from Issues.txt, triggers Codex | `issues`, `workflow_dispatch` |
| `pr-00-gate.yml` | CI enforcement with commit status | `pull_request` |
| `autofix.yml` | Auto-fixes lint/format issues | `pull_request`, `pull_request_target` |

### Required Scripts (in consumer repo)

**JavaScript scripts** (in `.github/scripts/`):
- `issue_pr_locator.js` - Locates PRs associated with issues
- `issue_context_utils.js` - Utilities for issue context extraction
- `issue_scope_parser.js` - Parses scope/tasks/acceptance from issue body
- `keepalive_instruction_template.js` - Generates keepalive instruction comments

**Python scripts** (in `.github/scripts/`):
- `decode_raw_input.py` - Decodes base64 input for ChatGPT sync
- `parse_chatgpt_topics.py` - Parses topics from ChatGPT format
- `fallback_split.py` - Fallback topic splitting logic

### Required Templates

- `.github/templates/keepalive-instruction.md` - Template for Codex instruction comments

### Required Secrets

| Secret | Purpose | Source |
|--------|---------|--------|
| `SERVICE_BOT_PAT` | Bot account for comments/labels | Classic PAT from bot account (e.g., stranske-automation-bot) |
| `ACTIONS_BOT_PAT` | Workflow dispatch triggers | PAT with `actions:write` scope |
| `OWNER_PR_PAT` | Create PRs on behalf of user | Owner's PAT |

**Important**: `SERVICE_BOT_PAT` must be a **Classic PAT**, not a fine-grained PAT. Fine-grained PATs cannot be created for bot accounts and lack the necessary cross-repo permissions.

### Required Repository Variables

| Variable | Purpose | Example |
|----------|---------|---------|
| `ALLOWED_KEEPALIVE_LOGINS` | Users allowed to trigger keepalive | `stranske,other-user` |

---

## Common Failures and Fixes

### 1. PR Number Type Conversion (PR #66)

**Symptom**: `pr_meta_comment` job silently skips; no dispatch happens.

**Root Cause**: GitHub Actions job outputs are always strings, but reusable workflows may expect `type: number`.

**Fix**: Use `fromJSON()` to convert string to number:

```yaml
# WRONG - pr_number is a string "123", but workflow expects number
pr_meta_comment:
  uses: stranske/Workflows/.github/workflows/reusable-20-pr-meta.yml@main
  with:
    pr_number: ${{ needs.resolve_pr.outputs.pr_number }}  # String!

# CORRECT - Convert to number
pr_meta_comment:
  uses: stranske/Workflows/.github/workflows/reusable-20-pr-meta.yml@main
  with:
    pr_number: ${{ fromJSON(needs.resolve_pr.outputs.pr_number) }}  # Number!
```

**Location**: `agents-pr-meta.yml`, lines calling reusable-20-pr-meta.yml

---

### 2. Missing JavaScript Scripts (PR #64)

**Symptom**: Agent bridge fails with "script not found" errors; bootstrap PRs don't get created.

**Root Cause**: The `reusable-agents-issue-bridge.yml` workflow expects certain scripts to exist in the consumer repo (not fetched via dual checkout).

**Fix**: Copy these scripts to `.github/scripts/` in consumer repo:
- `issue_pr_locator.js`
- `issue_context_utils.js`
- `issue_scope_parser.js`
- `keepalive_instruction_template.js`

**Source**: Copy from `stranske/Workflows/.github/scripts/`

---

### 3. Gate Completion Race Condition (PR #71)

**Symptom**: Human posts `@codex` comment, keepalive detects it with `gate-not-concluded`, but nothing happens after Gate passes.

**Root Cause**: When Gate completes, the pr-meta workflow isn't triggered because only `issue_comment` triggers were configured. The original comment is already processed.

**Fix**: Add `workflow_run` trigger for Gate completion:

```yaml
on:
  issue_comment:
    types: [created]
  pull_request:
    types: [opened, synchronize, reopened, edited]
  # ADD THIS - Re-evaluate keepalive when Gate completes
  workflow_run:
    workflows: ["Gate"]
    types: [completed]

jobs:
  # Handle Gate completion
  resolve_gate_pr:
    if: github.event_name == 'workflow_run' && github.event.workflow_run.conclusion == 'success'
    runs-on: ubuntu-latest
    outputs:
      pr_number: ${{ steps.resolve.outputs.pr_number }}
      should_process: ${{ steps.resolve.outputs.should_process }}
    steps:
      - name: Resolve PR from Gate run
        id: resolve
        uses: actions/github-script@v8
        with:
          script: |
            const run = context.payload.workflow_run;
            const prs = run.pull_requests || [];
            
            if (prs.length === 0) {
              core.setOutput('should_process', 'false');
              return;
            }
            
            const prNumber = prs[0].number;
            const { data: pr } = await github.rest.pulls.get({
              owner: context.repo.owner,
              repo: context.repo.repo,
              pull_number: prNumber
            });
            
            // Only process if PR has keepalive label
            const hasKeepalive = pr.labels.some(l => l.name === 'agents:keepalive');
            core.setOutput('should_process', hasKeepalive ? 'true' : 'false');
            core.setOutput('pr_number', prNumber);

  pr_meta_gate:
    needs: resolve_gate_pr
    if: github.event_name == 'workflow_run' && needs.resolve_gate_pr.outputs.should_process == 'true'
    uses: stranske/Workflows/.github/workflows/reusable-20-pr-meta.yml@main
    with:
      pr_number: ${{ fromJSON(needs.resolve_gate_pr.outputs.pr_number) }}
      event_name: 'workflow_run'
      event_action: 'completed'
      allow_replay: true  # CRITICAL - allows re-processing after Gate
```

**Key Input**: `allow_replay: true` - Without this, the keepalive detection considers the original comment "already processed" and won't dispatch.

---

### 4. Missing Python Scripts (PR #50)

**Symptom**: ChatGPT sync mode fails; issues don't get created from `Issues.txt`.

**Root Cause**: The agents-63-issue-intake workflow in ChatGPT sync mode requires Python scripts.

**Fix**: Copy these scripts to `.github/scripts/` in consumer repo:
- `decode_raw_input.py`
- `parse_chatgpt_topics.py`
- `fallback_split.py`

---

### 5. Issue Number Extraction Fails (PR #90)

**Symptom**: Warning "Unable to determine source issue for PR #XX" on Codex-generated PRs.

**Root Cause**: Branch naming pattern `codex/github-mention-chorecodex-bootstrap-pr-for-issue-#XX` doesn't match the regex `/issue-+([0-9]+)/i`.

**Fix**: Update `extractIssueNumberFromPull()` in `agents_pr_meta_keepalive.js`:

```javascript
// OLD - doesn't match verbose Codex branch names
const branchMatch = branch.match(/issue-+([0-9]+)/i);

// NEW - handles issue-XX, issue-#XX, and -#XX patterns
const branchMatch = branch.match(/issue-#?([0-9]+)/i) || branch.match(/-#([0-9]+)(?:$|[^0-9])/i);
```

**Location**: This fix should be in `stranske/Workflows/.github/scripts/agents_pr_meta_keepalive.js`

---

### 6. Gate Commit Status Not Posted

**Symptom**: Keepalive waits forever for Gate; `gate-not-concluded` never resolves.

**Root Cause**: The Gate workflow doesn't post a commit status, or posts it with wrong context name.

**Fix**: Ensure Gate workflow posts status with exact context `Gate / gate`:

```yaml
- name: Report Gate commit status
  uses: actions/github-script@v7
  env:
    STATE: ${{ steps.summarize.outputs.state }}
  with:
    script: |
      await github.rest.repos.createCommitStatus({
        owner: context.repo.owner,
        repo: context.repo.repo,
        sha: context.payload.pull_request?.head?.sha ?? context.sha,
        state: process.env.STATE,
        context: 'Gate / gate',  // MUST match this exactly
        description: 'Gate status',
        target_url: `${process.env.GITHUB_SERVER_URL}/${process.env.GITHUB_REPOSITORY}/actions/runs/${process.env.GITHUB_RUN_ID}`,
      });
```

---

### 7. Checkbox Duplication in Issues (PR body shows `- [ ] [ ]`)

**Symptom**: Task checkboxes appear doubled: `- [ ] [ ] Task text`

**Root Cause**: `Issues.txt` already contains `- [ ]` and `formatTasks()` in agents-63-issue-intake adds another.

**Fix**: Either:
1. Remove `[ ]` from `Issues.txt` (use plain `- Task text`)
2. Or update `formatTasks()` to skip lines that already have checkboxes:

```javascript
// Skip if already has checkbox
if (!inFence && /^[-*]\s+\[[ xX]\]/.test(tr)) {
  out.push(raw);  // Already has checkbox, preserve as-is
} else if (!inFence && /^[-*]\s+/.test(tr)) {
  out.push(raw.replace(/^\s*[-*]\s+/, '- [ ] '));
}
```

---

## Debugging Checklist

When keepalive isn't working, check in this order:

1. **Check workflow triggers**
   - Is `agents-pr-meta.yml` triggered on `issue_comment`?
   - Is `workflow_run` trigger configured for Gate?

2. **Check job outputs**
   - Look at `resolve_pr` job - is `pr_number` output set?
   - Is `fromJSON()` used when passing to reusable workflow?

3. **Check secrets**
   - Is `SERVICE_BOT_PAT` configured?
   - Is it a Classic PAT (not fine-grained)?

4. **Check variables**
   - Is `ALLOWED_KEEPALIVE_LOGINS` set with the right usernames?

5. **Check scripts exist**
   - Do all 4 JS scripts exist in `.github/scripts/`?
   - Do all 3 Python scripts exist?

6. **Check Gate status**
   - Does Gate post commit status with context `Gate / gate`?
   - Does it post on success AND failure?

7. **Check labels**
   - Does PR have `agents:keepalive` label?
   - Is the label applied automatically or manually?

8. **Check logs**
   - Look at `pr_meta_comment` or `pr_meta_pr` job logs
   - Search for "dispatch" or "keepalive" in output
   - Check for "gate-not-concluded" reason

---

## Architecture Diagram

```
Human posts "@codex <instructions>" on PR
         │
         ▼
┌─────────────────────────────────────┐
│  agents-pr-meta.yml                 │
│  (issue_comment trigger)            │
│                                     │
│  1. resolve_pr job extracts PR#     │
│  2. pr_meta_comment calls reusable  │
│     workflow with fromJSON(pr#)     │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│  reusable-20-pr-meta.yml            │
│  (in Workflows repo)                │
│                                     │
│  1. detectKeepalive() runs          │
│  2. Checks Gate status              │
│  3. If gate OK: dispatch orchestr.  │
│  4. If gate pending: wait           │
└─────────────────────────────────────┘
         │
         ├──► Gate not ready? ──► Wait for workflow_run trigger
         │
         ▼
┌─────────────────────────────────────┐
│  agents-70-orchestrator.yml         │
│  (workflow_dispatch trigger)        │
│                                     │
│  1. Finds PR with keepalive label   │
│  2. Posts instruction comment       │
│  3. Codex picks up and works        │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│  Codex works on PR                  │
│  Posts completion comment           │
│  (triggers agents-pr-meta again)    │
└─────────────────────────────────────┘
         │
         ▼
    Loop continues until done
```

---

## Version History

| Date | PR | Issue | Fix |
|------|-----|-------|-----|
| 2025-12-22 | #47 | Scripts missing | Added dual checkout for Workflows scripts |
| 2025-12-22 | #50 | Python scripts missing | Added decode_raw_input.py, parse_chatgpt_topics.py |
| 2025-12-22 | #64 | JS scripts missing | Added issue_pr_locator.js and 3 others |
| 2025-12-23 | #66 | pr_number type | Added fromJSON() conversion |
| 2025-12-23 | #71 | Gate race condition | Added workflow_run trigger with allow_replay |
| 2025-12-23 | #90 | Issue number regex | Updated extractIssueNumberFromPull() |

---

## Related Documentation

- [WORKFLOWS.md](../ci/WORKFLOWS.md) - CI workflow layout
- [AGENTS_POLICY.md](../AGENTS_POLICY.md) - Agent automation policy
- [INTEGRATION_GUIDE.md](../INTEGRATION_GUIDE.md) - Consumer repo integration
