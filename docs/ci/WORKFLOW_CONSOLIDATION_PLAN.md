# Workflow Consolidation Design (PR Context)

## Scope

Multiple PR-triggered workflows fetch identical pull request context (labels, body, files,
status) and run on the same events. This document proposes merged workflow designs that
fetch PR data once per event and fan out work via a job matrix.

## Audit snapshot and candidates

Use `scripts/workflow_pr_context_audit.py --only-pr-context` to refresh the list. The
current consolidation candidates (by manual review) fall into two clusters:

### Cluster A: PR event handlers (issue_comment / pull_request)

- `agents-pr-meta-v4.yml` (keepalive detection + PR metadata)
- `agents-bot-comment-handler.yml` (unresolved bot comment handling)
- `agents-verify-to-issue-v2.yml` (issue mirror/verification on PRs)

These share similar trigger events and independently pull PR data. They are good
candidates for a single workflow with shared context collection.

### Cluster B: Gate follow-ups (workflow_run on Gate)

- `agents-keepalive-loop.yml` (keepalive loop)
- `agents-autofix-loop.yml` (autofix loop)
- `maint-46-post-ci.yml` (post-CI recovery/summary)

These all wake on Gate completion, derive the PR number, then re-fetch the same PR data.

## Design A: PR Event Hub (matrix)

**Proposed workflow:** `agents-80-pr-event-hub.yml` (new)

**Triggers:** `issue_comment` (created), `pull_request` (opened/synchronize/reopened),
optional `workflow_dispatch` for debugging.

**Shared context job:**

- `pr_context` job calls `reusable-pr-context.yml` once.
- Outputs `pr_number`, `labels_json`, `pr_body`, `head_sha`, etc. for downstream jobs.

**Matrix job:**

```
handler: [pr-meta, bot-comments, verify-to-issue]
```

- Each handler runs with a conditional `if:` based on the event/labels.
- Each handler invokes its existing reusable workflow (or inlined steps) using
  `needs.pr_context.outputs.*`.

**Benefits:**

- One API pull for PR context per event.
- Shared concurrency and cancellation policies.
- Simplifies cross-workflow ordering (single DAG).

## Design B: Gate Follow-up Hub (matrix)

**Proposed workflow:** `agents-81-gate-followups.yml` (new)

**Triggers:** `workflow_run` for `Gate` (completed).

**Shared context job:**

- `gate_context` resolves the PR number from the workflow_run payload and uses
  `reusable-pr-context.yml` to fetch PR details once.

**Matrix job:**

```
handler: [keepalive, autofix, post-ci]
```

- Each handler uses `needs.gate_context.outputs.*` to avoid duplicate PR lookups.
- Handler jobs preserve existing success/failure semantics.

**Benefits:**

- Avoids repeated PR API calls after Gate completion.
- Keeps follow-ups in one workflow run for simpler tracking.

## Compatibility and guardrails

- Workflows using `pull_request_target` for privileged secrets remain isolated if
  mixed-permission execution would violate safety constraints.
- Notice period and deprecation flow must be documented before disabling legacy
  workflows (target: 2-4 weeks with clear README/WORKFLOW_GUIDE updates).

## Deprecation window (consumer repos)

**Deprecated (notice published):** 2026-01-15  
**Removal no earlier than:** 2026-02-15

Legacy workflows remain supported during the window while consumer repos migrate:

- `agents-pr-meta.yml` → `agents-80-pr-event-hub.yml`
- `agents-bot-comment-handler.yml` → `agents-80-pr-event-hub.yml`
- `agents-verify-to-issue-v2.yml` → `agents-80-pr-event-hub.yml`
- `agents-keepalive-loop.yml` → `agents-81-gate-followups.yml`
- `agents-autofix-loop.yml` → `agents-81-gate-followups.yml`

## Open questions

- Should bot-comment handling remain separate due to permission context or can it
  safely run in a shared workflow with `pull_request` triggers only?
- Does `agents-verify-to-issue-v2.yml` require additional permissions not shared by
  the other PR handlers?
