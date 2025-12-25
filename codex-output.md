Updated keepalive state updates to preserve any existing summary content by replacing or appending the `keepalive-state` marker instead of overwriting the whole comment, so the summary stays the single source of truth. This is implemented in `.github/scripts/keepalive_state.js` and verified with new/updated coverage in `.github/scripts/__tests__/keepalive-state.test.js` to ensure summary text survives state updates.

Tests run:
- `node --test .github/scripts/__tests__/keepalive-state.test.js .github/scripts/__tests__/keepalive-loop.test.js .github/scripts/__tests__/agents-pr-meta-update-body.test.js .github/scripts/__tests__/comment-dedupe.test.js`

Notes:
- Workflow-file changes (e.g., passing `agent_type` in `agents-pr-meta-v4.yml` or any other `.github/workflows/**` edits) still require a human with `agent-high-privilege`.

If you want next steps, I can:
1) Add a unit test for CLI label suppression of keepalive instruction comments.
2) Outline the exact workflow diffs needed for the remaining workflow-only tasks.