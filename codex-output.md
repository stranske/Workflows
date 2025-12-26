Emitted a structured keepalive metrics record from the summary step so each iteration can publish a JSON payload (including duration and task counts) for the collector to consume later. This centralizes the record assembly in the keepalive loop and exposes it via `metrics_record_json` for workflow wiring.

Details:
- Built helpers for optional numeric parsing, duration resolution, and metrics record construction in `.github/scripts/keepalive_loop.js`.
- Emitted a metrics record after each summary update, with a 1-based iteration and sensible defaults for action/error category in `.github/scripts/keepalive_loop.js`.

Tests not run (not requested).

Next steps:
1. Wire `metrics_record_json` into the collector invocation in the keepalive workflow (once workflow edits are allowed).
2. Add tests for the new metrics helpers and duration handling.
3. Run the relevant keepalive workflow tests to validate outputs end-to-end.