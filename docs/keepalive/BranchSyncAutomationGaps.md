# Keepalive Branch-Sync Automation Gaps

## 1) Comment/dispatch commands are orphaned
Keepalive post-work dispatches `update-branch` / `create-pr` as `repository_dispatch` events under the `codex-pr-comment-command` type, but no workflow listens for that event. The orchestrator only registers `agents-orchestrator-ping`, so the command payloads are effectively dropped before any branch-sync action can run.

**Suggested fixes**
- Add a lightweight `repository_dispatch` listener for `codex-pr-comment-command` that calls `pulls.updateBranch` (with polling) and, on failure, dispatches the branch-sync helper workflow with the same context. Alternatively, change `dispatchCommand` to target the existing branch-sync helper directly instead of the unused event type.
- Once implemented, emit a summary line when the command handler runs so PR-meta can observe the remediation path.

## 2) Fallback sync cannot fetch fork heads
The branch-sync helper allows a `head_repository` input so it can check out fork heads, but the keepalive post-work step never forwards the PR head repo. As a result, fallback dispatches default to the base repository and fail to fetch the head SHA for forked PRs, preventing the automatic "Update Branch" / "Create PR" remediation from landing.

**Suggested fixes**
- Export `HEAD_REPO` from `keepalive-prep` into the post-work environment and include it in `dispatchFallbackWorkflow` inputs so `agents-keepalive-branch-sync.yml` receives `head_repository`.
- Add a guardrail that bails out early with a clear summary if the head repo is missing for forked PRs instead of silently continuing with the wrong repository.
