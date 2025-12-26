Implemented the keepalive metrics dashboard generator and added unit coverage for both the collector and dashboard aggregation, then updated the PR task/acceptance checkboxes to reflect verified progress in `codex-prompt.md`.

Details:
- New dashboard script at `scripts/keepalive_metrics_dashboard.py` reads NDJSON, computes success rate/avg iterations/error breakdown, and writes a markdown table.
- Added collector validation/append tests in `tests/scripts/test_keepalive_metrics_collector.py`.
- Added dashboard aggregation tests for empty/single/multi inputs in `tests/scripts/test_keepalive_metrics_dashboard.py`.
- Marked completed tasks and acceptance criteria in `codex-prompt.md`.

Tests:
- `pytest tests/scripts/test_keepalive_metrics_collector.py tests/scripts/test_keepalive_metrics_dashboard.py`

Next steps:
1. Decide how to handle `agents-orchestrator.yml` updates (requires `agent-high-privilege` per repo policy).