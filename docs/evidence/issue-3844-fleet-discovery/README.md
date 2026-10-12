# Workflows3844 bounded discovery proof

Production workflow was restored byte-for-byte after substituting the original
unfiltered paginate(per_page=100) implementation. The selected test executed that
actual download script, produced one assertion failure (no errors/skips), then
passed after restoration. Commands, hashes, JUnit and raw output: proof.json,
red.log/red.xml, restored-green.log/restored-green.xml. This is a simulated
large-inventory transport control, not an actual hosted conformance cycle.

88 relevant Python checks and 8 Node checks pass. Broader raw output and JUnit
are retained. Node covers exact preference, trusted suffixes, expired/absent run
rejection, adaptive page/offset behavior, authorization failure, bounded UNKNOWN
and empty inventory. Six authored sentinel-shell executions verify new/existing
issue labels for healthy, code-owned degraded and missing-key degraded states.

The live GitHub exact-name request returned 12 matching artifacts using
GET /repos/stranske/Workflows/actions/artifacts?name=langsmith-fleet.ndjson&per_page=30.
Raw metadata is live-exact-artifacts.json. The separate unfiltered per_page=1
inventory-count read failed to parse; current total is UNKNOWN. The user issue's
31,260 count is historical evidence, not today's verified count. No existing
artifacts were deleted. Actual hosted full conformance and sentinel recovery
remain pending; source issue must stay open until those named gates complete.

Validation commands:
- node --test .github/scripts/__tests__/langsmith-fleet-artifacts.test.js
- /opt/anaconda3/bin/python3 -m pytest tests/workflows/test_langsmith_fleet_conformance_workflow.py tests/workflows/test_langsmith_observability_health_workflow.py tests/scripts/test_langsmith_observability_health.py tests/scripts/test_langsmith_fleet.py tests/scripts/test_langsmith_fleet_conformance.py tests/scripts/test_ensure_langsmith_fleet_artifact.py tests/docs/test_langsmith_observability_contract_doc.py tests/workflows/test_langsmith_metrics_dashboard.py -q -o addopts=
- actionlint -shellcheck= -pyflakes= .github/workflows/maint-80-langsmith-metrics-dashboard.yml .github/workflows/maint-81-langsmith-fleet-conformance.yml .github/workflows/health-84-langsmith-observability.yml
- python3 scripts/validate_template_completeness.py

Root-only maintenance: no consumer template or sync-manifest ownership changed.

Hosted Maint52 run38179428768 exposed the new helper API-wrapper guard failure.
The exact local guard reproduces RED then GREEN after routing listing reads
through github-api-with-retry.js with maxRetries=0, preserving adaptive 500
page reduction. Native run reads retain the shared wrapper and two retries.
Full 88 Python / 8 Node controls and the production reversal/restoration were
rerun after this change. See api-guard-red.log/api-guard-green.log.

The standard-environment deliberate-break gate is now repeatable in
`test_deliberate_break_unfiltered_enumeration_fails_then_restoration_passes`.
It substitutes the original unfiltered `paginate(per_page=100)` request in the
existing production harness input, requires the regression assertion to fail
with the simulated listing HTTP 500, removes the substitution, and requires the
production download to pass. The workflow bytes are checked unchanged.
No protected workflow file is edited, even temporarily.

The standalone production regression was also run under that in-memory
substitution: exit 1, one assertion failure, zero errors or skips. Removing the
temporary pytest plugin gave exit 0 and one passing test. Raw logs, JUnit, and
matching workflow hashes are retained in `standard-gate/`. This control remains
local simulated transport evidence; it adds no hosted conformance claim.

- [x] Deliberate-break gate: original unfiltered `per_page=100` enumeration fails
  the production regression, then unchanged production code passes.

Validation: `pytest tests/workflows/test_langsmith_fleet_conformance_workflow.py
tests/workflows/test_langsmith_observability_health_workflow.py
tests/scripts/test_langsmith_observability_health.py -m "not slow" -q` passed
28 tests; `node .github/scripts/__tests__/langsmith-fleet-artifacts.test.js`
passed 11 tests. Focused Ruff passed.
The required full-repository Black check passed: 698 files unchanged. The
installed Black 26.10.0 formatter ran with a local serial executor adapter after
sandbox process creation failed and the thread executor stalled; the formatter,
file selection, line length, and check mode were unchanged.
