# Keepalive Troubleshooting Guide

Keepalive advances an opted-in pull request through its remaining tasks. Trace
the exact repository, PR number, current head SHA, workflow run ID and attempt.
A completed Actions run can represent a skip, an unproductive worker, or progress.

## Find the right run

| Entry point | Workflows repository | Consumer repositories |
| --- | --- | --- |
| Gate completes | [Agents Keepalive Loop](../../.github/workflows/agents-keepalive-loop.yml), `evaluate` | [Agents Gate Followups](../../templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml), `evaluate`, with `USE_CONSOLIDATED_WORKFLOWS=true` |
| Periodic recheck | [Agents Keepalive Sweep](../../.github/workflows/agents-keepalive-sweep.yml), `sweep` | [Agents Keepalive Sweep](../../templates/consumer-repo/.github/workflows/agents-keepalive-sweep.yml), `name_mode` then one of `sweep_consolidated` or `sweep_nonconsolidated` |
| PR metadata and Workflows comment activation | [Agents PR meta manager](../../.github/workflows/agents-pr-meta-v4.yml) | [Agents PR Event Hub](../../templates/consumer-repo/.github/workflows/agents-80-pr-event-hub.yml), `resolve` then `pr_meta` |
| Failure or cancellation before feedback | [Keepalive Loop Reporter](../../.github/workflows/agents-keepalive-loop-reporter.yml) | [Keepalive Loop Reporter](../../templates/consumer-repo/.github/workflows/agents-keepalive-loop-reporter.yml), in either consumer sweep mode |

Both consumer sweep jobs manually dispatch Gate Followups. The sweep picks open,
non-draft PRs with `agents:keepalive` and an `agent:*` label. On an unchanged PR
it can re-evaluate a stalled round even when no new Gate event arrives.
For a comment-based command, follow the [activation path](Observability_Contract.md#comment-activation).
An ordinary Gate or sweep wake uses labels and PR state.

## Diagnose the first skipped or failed step

1. **Read the sweep or Gate origin.** Confirm the PR was selected or bound to
   the Gate run. If GitHub omits a PR association, the evaluator can resolve it
   from the run head. On a consumer, `name_mode` tells you which sweep job
   should run.
2. **Open `evaluate`.** Read `action`, `reason`, `gate_conclusion`,
   `agent_type` and `dispatch_reason`. Check pause and cap labels, remaining
   work, the current Gate result and retry state. For a trusted fork, trace the
   [required status publishers](FORK_GATE_STATUS_PUBLICATION.md).
3. **Open `acceptance-gates` and `preflight` on Workflows, or `preflight` on a
   consumer.** Look for deterministic acceptance results where enabled, the
   selected runner environment, required credential checks and trusted summary
   writer setup. See the [agent registry](../../.github/agents/registry.yml)
   and [consumer setup](SETUP_CHECKLIST.md).
4. **Open the selected `run-<agent>` job.** Check its exact attempt and push
   result. An exit-zero provider can still produce no work. Compare the
   reserved head to the current head and inspect the runner's own evidence.
5. **Read `finish` and the Automated Status Summary.** Check task
   reconciliation, the agent outcome, and `Record completion`. An unreadable
   head leaves productivity unmeasured. If the run failed or was cancelled,
   inspect the reporter's `resolve-target` and `report` jobs. Missing or
   conflicting worker evidence leaves the authority obligation unresolved.
   See [feedback and recovery](Observability_Contract.md).

## Historical Travel-Plan-Permission incidents

The following notes preserve the December 2025 investigation (PRs #47–#94).
Their workflow names, versions, token requirements and commands describe that
installation at the time. The workflows above are the current entry points.

## Common Failures and Fixes

### 1. PR Number Type Conversion (PR #66)

**Symptom**: `pr_meta_comment` job silently skips; no dispatch happens.

**Root Cause**: GitHub Actions job outputs are always strings, but reusable workflows may expect `type: number`.

**Fix**: Use `fromJSON()` to convert string to number:

```yaml
# WRONG - pr_number is a string "123", but workflow expects number
pr_meta_comment:
  uses: stranske/Workflows/.github/workflows/reusable-20-pr-meta.yml@v1
  with:
    pr_number: ${{ needs.resolve_pr.outputs.pr_number }}  # String!

# CORRECT - Convert to number
pr_meta_comment:
  uses: stranske/Workflows/.github/workflows/reusable-20-pr-meta.yml@v1
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
    uses: stranske/Workflows/.github/workflows/reusable-20-pr-meta.yml@v1
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
