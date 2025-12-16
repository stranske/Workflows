# CI Autofix Loop

The `CI Autofix Loop` workflow (`.github/workflows/autofix.yml`) runs after the
primary `PR 00 Gate` workflow finishes with a failure on automation-owned pull
requests. Its only purpose is to repair trivial lint and formatting drift so the
main Codex change set can progress without manual intervention.

## Trigger conditions

The workflow receives `workflow_run` events from `PR 00 Gate` and immediately
exits unless *all* of the following checks succeed:

- The upstream run concluded with `failure`.
- The upstream run targeted a pull request labelled with both:
  - `agent:*` (any agent automation label, e.g. `agent:codex`).
  - `autofix` (explicit opt-in for the bounded loop).
- The pull request is open, not draft, lives in this repository (no forks), and
  the head SHA still matches the failing run.
- Fewer than two autofix attempts have already run for the current head SHA.

When these gates pass the workflow increments the attempt counter (stored in a
marker comment on the pull request) and continues. Attempts are capped at two to
avoid churn—subsequent failures require manual follow-up.

## Branch strategy

Repairs never touch the contributor's branch directly. Instead the workflow:

1. Checks out the failing head commit.
2. Creates an ephemeral branch named `autofix/<pr-number>-<short-sha>`.
3. Runs the safe autofix sweep on that branch.
4. Pushes the branch if changes were produced.

This keeps the source branch clean while still exposing a reviewable diff that
Gate can validate independently.

## Safe operations

The automation intentionally limits itself to cosmetic fixes. The current sweep
installs the repository's pinned Ruff version (from
`.github/workflows/autofix-versions.env`) and runs:

```bash
ruff check --select I --fix .
ruff format .
```

After running these commands the workflow inspects the resulting diff and aborts
if any touched file falls outside the Python globs `**/*.py` or `**/*.pyi`. This
guarantees that only import-order and formatting edits are staged. When no files
change the branch push is skipped, but the attempt is still recorded for
traceability.

## Reporting & labelling

Every run updates (or creates) a dedicated comment on the pull request with a
concise summary:

- Attempt counter and trigger run.
- Target branch and head SHA.
- Whether a branch push occurred.
- The list of touched files (if any).

The comment stores metadata in a `<!-- autofix-loop:{...} -->` marker so future
runs can detect prior attempts. When the sweep produces formatting/import-order
changes it applies the `autofix:clean` label and clears `needs-autofix-review`.
If no edits were produced (or a future expansion detects non-cosmetic work) the
labels flip: `needs-autofix-review` is added and `autofix:clean` is removed so a
human can take over. If the job is skipped the guard reason is emitted to the
job summary for quick inspection.

## Failure modes

The job fails fast if:

- The `ACTIONS_BOT_PAT` secret is missing.
- Tooling cannot be installed.
- Disallowed files were modified by the sweep.
- Git operations (commit/push) fail.

In all cases the guard summary records the skip or failure reason so maintainers
can triage the remaining CI issues manually.
