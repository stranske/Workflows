# LangSmith Fleet Observability Contract

This document defines the fleet-level LangSmith observability program contract
owned by Workflows.

For the wire format, use
[`langsmith-fleet/v1`](./langsmith-fleet-v1.md).

## Ownership Boundary

Workflows owns:

- the shared `langsmith-fleet/v1` record contract,
- the fleet registry (`config/langsmith_fleet_registry.json`),
- validation tooling (`scripts/langsmith_fleet.py`),
- dashboard ingestion and status rollup (`missing`, `invalid`, `stale`,
  `valid`).

Consumer repos own:

- domain instrumentation and where traces are emitted,
- operation naming inside their repo surface,
- domain metadata values under `domain`.

Consumer repos must emit artifacts that match the shared contract and registry
requirements, but they should keep repo-specific instrumentation logic local.

## Shared vs Domain Metadata

Use shared fields for fleet comparability:

- identity and rollout tracking (`repo`, `surface`, `operation`,
  `github_issue`),
- run-level status (`status`, `recorded_at`),
- optional normalized metrics (`latency_ms`, `cost_usd`),
- safe trace and payload references (`trace_id`, `trace_url`, hashes,
  artifact refs).

Use `domain` for repo-specific details that are meaningful inside a repo
context and required by the registry entry for that surface.

Never put raw prompts, personal data, SQL rows, or full model output in shared
or domain fields. Use hash or artifact references instead.

## Registry And Rollout Tracking

Every participating repo/surface must have a registry entry that defines:

- repo,
- issue number,
- surface,
- operation family,
- required `domain` fields,
- artifact name,
- rollout status.

Current tracked implementation issues:

- `stranske/trip-planner#1208`
- `stranske/Pension-Data#445`
- `stranske/Manager-Database#1048`
- `stranske/Counter_Risk#610`
- `stranske/Inv-Man-Intake#438`
- `stranske/Trend_Model_Project#5311`
- `stranske/Portable-Alpha-Extension-Model#1802`

## Validation Expectations

Validation must succeed when `LANGSMITH_API_KEY` is unset.

Validation must fail for malformed records, including:

- invalid JSON lines,
- missing required shared fields,
- unknown repo/surface mappings,
- missing required domain fields,
- unsafe raw payload values,
- invalid status values.

Workflows runs a fleet conformance check from
`.github/workflows/maint-81-langsmith-fleet-conformance.yml`. The check reads
each registry entry, downloads the latest per-repo `langsmith-fleet.ndjson`
artifact when one exists, and validates it with `scripts/langsmith_fleet.py`.
The scheduled path is warning-only: missing, stale, or invalid rows emit
workflow warnings and a machine-readable report artifact, but they do not block
the weekly run. Manual dispatch can set `enforce_block=true` to fail the
workflow for non-`valid` rows when maintainers intentionally want a hard gate.

## Repo Issue Implementation Checklist

Each repo-specific LangSmith implementation issue should keep instrumentation
logic local while proving compatibility with the shared Workflows contract:

1. Keep tracing and instrumentation code in the consumer repo, not in
   Workflows.
2. Emit a `langsmith-fleet.ndjson` artifact that validates as
   `langsmith-fleet/v1`.
3. Populate shared fields (`repo`, `surface`, `operation`, `github_issue`,
   `status`, `recorded_at`) exactly as defined by the registry entry.
4. Populate only repo-specific details in `domain`, including every required
   domain field from the registry.
5. Avoid raw prompts/output/PII; publish references and hashes instead.
6. Include a link back to the parent Workflows LangSmith fleet issue so rollout
   status can be tracked centrally.

## Dashboard Status Contract

Dashboard ingestion distinguishes four states per registry entry:

- `missing`: artifact not found,
- `invalid`: artifact exists but fails validation,
- `stale`: latest valid record is older than the freshness window,
- `valid`: at least one current valid record is present.

The conformance report artifact uses the same status vocabulary and includes
`repo`, `surface`, `issue`, `artifact_name`, `record_count`,
`latest_recorded_at`, `status`, and `first_error` for every registry row. An
uploaded artifact with malformed records is reported as `invalid` for the
owning repo/surface even when the malformed rows omit routing fields such as
`surface`, `run_id`, or `github_issue`; missing routing fields must not be
silently downgraded to `missing`.
