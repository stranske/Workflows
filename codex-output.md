Implemented gate-summary suppression for agent-labeled PRs by short‑circuiting comment upserts when an `agent:*` label is present, and added coverage for that behavior. Updated the task appendix to reflect the verified Conditional Status Summary and keepalive summary work.

Details
- Gate summary skip logic lives in `.github/scripts/comment-dedupe.js`; it now checks PR labels before upserting gate summaries.
- Added a unit test in `.github/scripts/__tests__/comment-dedupe.test.js` to ensure no comment is created/updated when an `agent:*` label is present.
- Checked off verified tasks and updated progress in `codex-prompt.md`.

Tests
- `node --test .github/scripts/__tests__/comment-dedupe.test.js .github/scripts/__tests__/agents-pr-meta-update-body.test.js .github/scripts/__tests__/keepalive-loop.test.js`

Next steps
1. Run the pipeline validation steps on a real PR with `agent:codex` to verify keepalive updates and prompt appendix visibility.
2. Apply the remaining workflow‑file changes (e.g., `agents-pr-meta` and gate summary gating) via a human‑approved edit, since `.github/workflows` is protected.