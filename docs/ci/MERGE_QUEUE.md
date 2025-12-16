# Agent Merge Queue & Auto-merge Guide

The Codex orchestrator can automatically land automation-authored pull requests
once CI succeeds and the request is explicitly approved for merge. This guide
captures the optional merge queue setup for the repository and documents how
the new **Agent auto-merge** job works.

## Auto-merge prerequisites

Agent pull requests qualify for automatic merging only when all of the
following are true:

1. The pull request carries the `automerge` label.
2. The author is the automation account (`stranske-automation-bot`).
3. The base branch equals the repository's default protected branch.
4. The PR is not a draft and has no merge conflicts.
5. Every required check for the head commit finished successfully (the Gate
   workflow and any repository-mandated status checks).
6. Branch protection does not block merges (for example, outstanding review
   requirements or failing conversations).

The orchestrator job publishes a summary titled **Agent auto-merge scan** during
every run. It records the result for each labelled pull request and explains why
any candidate could not merge.

## Enabling the GitHub merge queue (optional)

Repositories that want GitHub's merge queue in addition to agent auto-merge
should:

1. Visit **Settings → Branches → Branch protection rules**.
2. Choose the default branch rule and enable **Require merge queue**.
3. Confirm the rule lists the checks that Gate already enforces (for example,
   `Gate / gate`).
4. Save the rule and ensure the repository has sufficient GitHub Actions
   concurrency for queued merges.

GitHub automatically places qualifying PRs in the queue after required checks
pass. Agent PRs that satisfy the prerequisites above still need the `automerge`
label to opt in to the orchestrator's merge call. Removing the label drops the
PR out of the automation flow.

## Daily workflow for agent PRs

1. Allow the Codex belt to open or update the automation PR.
2. Review CI results. When the Gate job and required checks pass, apply the
   `automerge` label if the change is ready to ship.
3. The orchestrator's auto-merge step waits for the queue (if enabled) and then
   squashes the PR into the default branch.
4. After merge, the job logs the successful completion in the workflow summary
   and removes the PR from future scans.

## Troubleshooting skipped merges

If the summary reports `skipped` or `error` for a pull request:

- Confirm the author is `stranske-automation-bot`. Human-authored PRs are
  intentionally ignored.
- Check that all required checks have completed. Pending or failing jobs will
  block auto-merge until they succeed.
- Verify the PR targets the default branch and is up to date. Branch protection
  may require a rebase or force a manual review before merging.
- Ensure no one removed the `automerge` label or re-opened review threads.
- If branch protection continues to block the merge, the summary includes the
  exact reason (for example, `mergeable_state=blocked`). Address the underlying
  rule or merge manually when appropriate.

When the queue is enabled, GitHub's UI also lists each PR's queue state. Use it
alongside the orchestrator summary to diagnose delays.
