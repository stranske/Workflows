Added non‑transient failure escalation to the keepalive summary flow, posting an attention comment with recovery guidance and applying the `agent:needs-attention` label, plus tests that validate the PR comment text for auth/resource/logic failures; also reconciled the task checklist. Key updates live in `.github/scripts/keepalive_loop.js` and `.github/scripts/__tests__/keepalive-loop.test.js`, with task status updates in `codex-prompt.md`.

Tests: `node --test --test-reporter spec .github/scripts/__tests__/keepalive-loop.test.js`

Blocked: workflow changes in `.github/workflows/reusable-codex-run.yml` are required by the next unchecked tasks, but that path is protected in `agent-standard`. A human (or `agent-high-privilege`) needs to implement the failure classification step, conditional retry for transient errors, step summary output, and diagnostics artifact creation, and add the `needs-human` label/comment per repo policy.

Next steps:
1. Apply the required edits to `.github/workflows/reusable-codex-run.yml` under `agent-high-privilege` (or by a maintainer).
2. If you want, I can proceed with any remaining non-workflow tasks once the above is handled.