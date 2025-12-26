Added a keepalive metrics smoke test and harness so we can validate a real keepalive summary emits a schema‑correct record that can be appended, plus a focused JS test to assert the `metrics_record_json` output shape; updated the PR body checkbox to mark the integration smoke test as done. Changes are in `.github/scripts/__tests__/keepalive-loop.test.js`, `tests/scripts/test_keepalive_metrics_integration.py`, `tests/scripts/fixtures/keepalive_metrics/harness.js`, and `codex-prompt.md`.

Tests:
- `node --test .github/scripts/__tests__/keepalive-loop.test.js`
- `pytest -q tests/scripts/test_keepalive_metrics_integration.py`

Blocked workflow update (needs-human):
- There is no `.github/workflows/agents-orchestrator.yml` in this repo; the keepalive loop currently lives in `.github/workflows/agents-keepalive-loop.yml` and already has an `Emit keepalive metrics` step with a different schema.
- Suggested change for a human: in `.github/workflows/agents-keepalive-loop.yml`, add an `id` to the “Update summary comment” step (so `metrics_record_json` can be consumed), then call `scripts/keepalive_metrics_collector.py` with that output after the keepalive run; remove or replace the existing jq‑based metrics step to avoid schema drift.
- Per repo policy, please add a `needs-human` label for the workflow edit.

Next steps:
1) Approve a high‑privilege run so I can update the workflow file (and align the schema), or apply the change manually.
2) If desired, run the broader workflow tests once the workflow change is in place.