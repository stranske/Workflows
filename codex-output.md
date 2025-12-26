Added the keepalive metrics schema doc and a collector script that validates records and appends NDJSON entries for each iteration. The collector supports either a JSON payload or individual CLI fields, enforces required types, and auto-fills timestamps when missing in JSON input. Files: `docs/keepalive/METRICS_SCHEMA.md`, `scripts/keepalive_metrics_collector.py`.

Tests run: `python -m pytest tests/scripts/test_aggregate_agent_metrics.py`

Next steps:
1. Integrate metrics emission into `.github/scripts/keepalive_loop.js`.
2. Add the dashboard generator plus tests for collector and dashboard.
3. Plan a human-approved update for `.github/workflows/agents-orchestrator.yml` (workflow edits are restricted in `agent-standard`).