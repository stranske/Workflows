Added an automatic default metrics log path for keepalive iterations running under GitHub Actions so records are appended without extra inputs, and expanded keepalive-loop tests to verify the default log behavior and clean up the workspace file. Updated the acceptance checkbox in `codex-prompt.md` after verifying the new logging behavior. Changes are in `.github/scripts/keepalive_loop.js`, `.github/scripts/__tests__/keepalive-loop.test.js`, and `codex-prompt.md`.

Tests: `node --test .github/scripts/__tests__/keepalive-loop.test.js`

Workflow update is still blocked by policy: I can’t edit `.github/workflows/agents-orchestrator.yml` in this run. Please add a `needs-human` label and a PR comment instructing the workflow update to call `scripts/keepalive_metrics_collector.py` after keepalive completes (or set `KEEPALIVE_METRICS_PATH` for the loop).

Next steps:
1) Have a human update `.github/workflows/agents-orchestrator.yml` to invoke the metrics collector or set `KEEPALIVE_METRICS_PATH`.
2) Run the full selftest CI to satisfy the remaining acceptance criterion.