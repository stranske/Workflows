Added an optional NDJSON append path to keepalive loop metrics so iterations can write structured records directly when `KEEPALIVE_METRICS_PATH` (or `metrics_path` input) is set, plus a test that verifies the file output. This keeps the metrics logging requirement moving forward while the workflow change is blocked by repository policy. Changes are in `.github/scripts/keepalive_loop.js` and `.github/scripts/__tests__/keepalive-loop.test.js`.

Tests: `node --test .github/scripts/__tests__/keepalive-loop.test.js`

Blocked item: Updating `.github/workflows/agents-orchestrator.yml` requires `agent-high-privilege`; I can’t edit workflows in this run. Please add a `needs-human` label and a PR comment noting the required workflow change: call `scripts/keepalive_metrics_collector.py` after keepalive completes or set `KEEPALIVE_METRICS_PATH` so `updateKeepaliveLoopSummary` appends to the NDJSON log.

Next steps:
1) Have a human update `.github/workflows/agents-orchestrator.yml` to invoke the collector or export `KEEPALIVE_METRICS_PATH`.