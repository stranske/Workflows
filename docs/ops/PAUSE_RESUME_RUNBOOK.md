# Pause And Resume Runbook

The active PR pause and its legacy spelling have a single-PR scope. The
former repository-wide pause is documented separately below.

## One PR: `agents:paused`

Use `agents:paused` when a single pull request should stop keepalive dispatch.

- Scope: one PR.
- Consumer: `.github/scripts/keepalive_gate.js` (`PAUSE_LABEL`).
- Pause: add `agents:paused` to the PR.
- Resume: remove `agents:paused` from the PR, then allow the next Gate or
  keepalive event to run.
- Pair with a PR comment when a human decision is required.

## Former Repository-Wide Pause: `keepalive:paused`

The retired Agents 70 resolver paused a repository's keepalive when this label
existed, regardless of whether it was applied to a PR. Its summary exposed
`keepalive_pause_label`.

Restoring that repository-wide control remains open after Agents 70 retirement.
The current keepalive routes have no verified equivalent for this label.

## Legacy Alias: `agents:pause`

`agents:pause` exists in `.github/labels-core.yml` as a legacy alias. Prefer
`agents:paused` for new incident handling, but do not treat `agents:pause` as a
no-op while older automation still recognizes it.

- Scope: one PR.
- Consumers: `.github/scripts/keepalive_loop.js` and reusable PR-health checks
  still include `agents:pause` in their pause-label sets; `keepalive_gate.js`
  only checks the canonical `agents:paused` spelling.
- Operator rule: apply `agents:paused` for new pauses.
- Migration rule: when an existing PR already has `agents:pause`, either leave
  it in place until the human blocker is resolved or replace it with
  `agents:paused` in the same operation. Removing it by itself can resume
  keepalive unexpectedly.

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
