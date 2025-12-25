Updated keepalive failure handling to classify failures (codex vs infrastructure), reset transient failure counters, and emit error classification in state/outputs; added transient failure coverage in ` .github/scripts/__tests__/keepalive-loop.test.js`; updated task checklist progress in `codex-prompt.md` to reflect verified work. This centers on ` .github/scripts/keepalive_loop.js` so the summary comment and state now track `error_type`/`error_category` and avoid pausing for transient issues.

Tests run:
- `node --test .github/scripts/__tests__/error-classifier.test.js`
- `node --test .github/scripts/__tests__/github-api-retry.test.js`
- `node --test .github/scripts/__tests__/keepalive-loop.test.js`

Blocked items:
- Workflow updates in `.github/workflows/reusable-codex-run.yml` are protected; I can’t edit them without `agent-high-privilege`. You’ll need a human/privileged run to apply the failure-handling steps there.

Next steps:
1) Apply the failure-handling changes in `.github/workflows/reusable-codex-run.yml` with privileged access.
2) Tackle the “unrecoverable failure” PR comment + `agent:needs-attention` labeling tasks once workflow changes are in place.