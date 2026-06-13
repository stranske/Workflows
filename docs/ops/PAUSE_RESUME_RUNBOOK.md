# Pause And Resume Runbook

Workflows has three pause spellings with different scopes. Pick the label by
scope first; do not treat the names as interchangeable.

## One PR: `agents:paused`

Use `agents:paused` when a single pull request should stop keepalive dispatch.

- Scope: one PR.
- Consumer: `.github/scripts/keepalive_gate.js` (`PAUSE_LABEL`).
- Pause: add `agents:paused` to the PR.
- Resume: remove `agents:paused` from the PR, then allow the next Gate or
  keepalive event to run.
- Pair with a PR comment when a human decision is required.

## One Repo: `keepalive:paused`

Use `keepalive:paused` when every keepalive run in a repository should stop.

- Scope: one repository.
- Consumer: `.github/scripts/agents_orchestrator_resolve.js`
  (`KEEPALIVE_PAUSE_LABEL`).
- Pause: create the `keepalive:paused` label in the repository. The orchestrator
  pauses when the label exists, even if it is not applied to any issue or PR.
- Resume: delete the `keepalive:paused` label from the repository.
- Verify: rerun or inspect the orchestrator summary for the
  `keepalive_pause_label` output.

## Do Not Use: `agents:pause`

`agents:pause` exists in `.github/labels-core.yml`, but no active workflow or
script consumes it as a pause control.

- Scope: none.
- Effect: no-op decoy.
- Operator rule: do not apply it during incident handling.
- If it was applied accidentally, remove it and apply `agents:paused` or create
  `keepalive:paused`, depending on the intended scope.

## Fleet-Wide Pauses

Fleet-wide pauses are owned by the local lane handoff policy, not by a GitHub
label. Prefer narrow scoped blockers for a single PR, issue, or repo. Request a
global pause only when the same blocker affects the whole supported fleet and no
repo-local workaround exists.

## Resume Checklist

1. Remove the relevant pause control.
2. Confirm no durable human blocker remains, such as `needs-human` or
   `agent:needs-attention`.
3. Confirm the PR still has one concrete `agent:<name>` label and
   `agents:keepalive`.
4. Add `agent:retry` when an immediate keepalive dispatch is needed.
5. Record the decision in the PR or issue so the next lane can see why work
   resumed.
