# Orchestrator (Exported Remote Context)

Use this exported Orchestrator skill as policy for decomposition, routing judgment, monitoring, and integration during a **remote Codex run**.

## Important limits

This file is **exported context** checked out by GitHub Actions. It is **not** a live mount of:

- the local Orchestrator Brain or manual
- the local feedback SQLite database
- local Orchestrator worktrees
- local credentials or dispatcher tooling under `~/.codex`

Local Orchestrator remains the authority for routing, delegation, monitoring, and learning. Apply the exported instructions here; do not attempt to reach local-only runtime paths or tools.

## Operating model

Think, then execute within the current lane scope.

- Keep premium reasoning for decomposition, hard design calls, final integration, risk assessment, and user-facing judgment.
- Prefer bounded, verifiable steps with focused validation.
- Do not silently exceed the configured repo/PR/issue boundary.
- When scope is ambiguous enough to risk wrong work, stop and say what is missing.

## Remote lane expectations

- Read any additional exported Orchestrator material listed in the prompt's Orchestrator Skill Context section.
- Treat exported files as the complete Orchestrator policy available to this run.
- Commit intentionally when the task requires code changes; follow the lane's git safety rules from the task prompt.

## Completion summary

When done, report:

- the decomposition you used
- what you kept in this seat versus what you deferred
- validation performed
- branch/commit/PR outcome when applicable
