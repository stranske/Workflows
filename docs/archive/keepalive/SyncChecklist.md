# Keepalive Sync Checklist

> **Always review the canonical contract in [`GoalsAndPlumbing.md`](GoalsAndPlumbing.md) before applying these recovery steps.**

Automation agents must consult this document whenever work touches the keepalive reconciliation path. It records the guardrails
for recovering when a Codex round reports "done" but no commit lands on the PR branch.

## Branch Recovery Sequence

1. **Snapshot before instruction** – `agents-70-orchestrator.yml` captures the head SHA, head ref, and base ref when posting the
   keepalive instruction comment. Those values seed the comparison logic below.
2. **Short poll (≤120s)** – After the worker reports success, poll the PR head for up to the short TTL. If a new SHA appears,
   the sync loop stops and the next keepalive instruction may proceed.
3. **Update-branch dispatch** – When the head remains unchanged, emit a `codex-pr-comment-command` repository dispatch with
   `action: 'update-branch'` using the issue number, base branch, working branch, keepalive trace, and comment metadata.
   Continue polling for the long TTL; success requires a new head SHA.
4. **Create-pr fallback** – If update-branch fails or the branch changed mid-run, send a second dispatch with
   `action: 'create-pr'`. Auto-merge the connector's PR back into the working branch (squash by default) and delete the
   temporary branch once merged. Poll again for a fresh head SHA.
5. **Escalate when still stale** – When no commit arrives after both attempts, apply the `agents:sync-required` label, skip the
   next keepalive instruction, and (only when `agents:debug` is present) post a single-line escalation comment:
   `Keepalive {round} {trace} escalation: agent "done" but branch unchanged after update-branch/create-pr attempts.`

All steps append outcomes to the job summary with the active `{trace}` so future rounds can correlate actions with their logs.

## Label Semantics

- **`agents:sync-required`** pauses subsequent keepalive rounds. The guard refuses to post new instructions until the label is
  cleared by a successful sync cycle.
- **`agents:debug`** enables the escalation comment on failure. Without it, the workflow records the summary only.

## Connector Payload Contract

Every repository dispatch emitted during keepalive sync must include:

```json
{
  "action": "update-branch" | "create-pr",
  "issue": <issue number>,
  "base": "<base branch>",
  "head": "<working branch>",
  "comment_id": <instruction comment id>,
  "comment_url": "<instruction comment url>",
  "agent": "codex",
  "trace": "<keepalive trace>",
  "round": <keepalive round>
}
```

The connector is responsible for staging commits and creating the temporary PR used by the fallback merge.

## When to Clear the Pause Label

`agents:sync-required` is removed automatically when a new head SHA appears after any of the recovery steps. Do **not** remove the
label manually unless you have confirmed that the branch advanced and the sync job completed successfully. Doing so breaks the
keepalive contract and risks reissuing instructions against stale code.
