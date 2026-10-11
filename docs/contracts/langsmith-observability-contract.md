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

An intentional `paused` rollout must also record `paused_at`, `pause_reason`,
`pause_owner`, `resume_condition`, and `review_by`. Registry validation rejects
an unowned or open-ended pause. The review date is an observability deadline,
not an automatic resume instruction: the owner must either resume the named
transport or renew the pause with current evidence.

## Independent State Axes

Never use one status to describe the whole observability system. Report these
axes independently:

1. **Rollout intent** — whether a particular registry transport is active or
   intentionally paused.
2. **Cloud trace flow** — whether the LangSmith project has a trace inside its
   freshness objective.
3. **Artifact conformance** — whether a repo's exported NDJSON is `missing`,
   `invalid`, `stale`, or `valid`.
4. **Durable local import** — whether Orchestrator has copied trace references,
   execution metadata, and costs into its local feedback database.

A paused artifact expectation does not mean cloud tracing is paused. Likewise,
a current cloud trace does not prove that Orchestrator imported it or that an
application-specific runtime is instrumented.

## Trace History And Orchestrator Access

The `workflows-agents` LangSmith project is the cloud source for trace payloads
and its history remains subject to the active LangSmith plan's retention rules.
Orchestrator can query that history directly and shapes joinable runs into the
same `langsmith-fleet/v1` execution records used by artifact ingestion.

Orchestrator then keeps imported `execution_traces` and `costs` rows in its
local SQLite feedback store indefinitely. Those durable rows contain trace IDs,
URLs, provider/model/status, latency, cost, and join references; they are not a
second copy of full prompts and outputs. Semantic trace inspection therefore
still requires the corresponding cloud trace to remain retained and accessible.

## Health And Notification Protocol

`health-84-langsmith-observability.yml` runs daily and supports manual
dispatch. It independently checks:

- the dashboard and conformance workflows have a success within 192 hours,
- neither workflow has two consecutive non-successful completed runs,
- `workflows-agents` has a cloud trace within 24 hours, and
- every intentional pause has valid ownership and resumption metadata. An overdue
  `review_by` remains visible as an advisory and does not degrade health.

The sentinel uploads its JSON/markdown evidence and upserts one durable health
issue. Code-owned degradation adds `agent:needs-attention`; only an unavailable
cloud credential adds `needs-human`. Workflow listing failures, stale conformance,
and sentinel execution failures remain automation-owned. Recovery removes the
labels; an owned degradation removes a stale `needs-human` label. This turns a pull-only warning or red scheduled run into
a durable surface consumed by normal triage.

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


## Bounded artifact discovery and retention

Conformance queries the exact artifact name server-side first. Legacy prefixed
names use a bounded small-page fallback and still require a registered trusted
producer workflow. Expired artifacts are excluded. Listing 500/502/503/504 errors
reduce the page size from 30 to 10 to 1, preserving the offset rather than repeating
the same oversized request. Exhausting the 30-request discovery budget fails with
UNKNOWN; it never establishes that evidence is absent or conformance passed.
The first eligible page is sorted newest-first; this bounded discovery does not
claim a complete historical repository inventory. Exact-name artifacts retain
the existing preference over legacy suffix matches.

Workflows retention policy for new uploads: routine CI diagnostics keep their
existing seven-day retention; daily/weekly LangSmith dashboard, conformance and
health snapshots retain 30 days (more than three weekly cycles). Durable verifier,
trial and coverage proof retain their explicitly declared 90-day exceptions.
These upload-level limits do not delete existing artifacts or change repository
settings, LangSmith storage, source archives or local metrics rollups. Future
artifact callers must use filtered/bounded discovery even when retention is set.

Validation: `node --test .github/scripts/__tests__/langsmith-fleet-artifacts.test.js`
and `python3 -m pytest tests/workflows/test_langsmith_fleet_conformance_workflow.py
 tests/workflows/test_langsmith_observability_health_workflow.py
 tests/scripts/test_langsmith_observability_health.py -q -o addopts=`. The authored
workflow test executes the production download script against a >30k-inventory
simulation; restoring the old unfiltered `paginate(per_page=100)` must fail.
Raw RED/restored GREEN logs, JUnit and hashes are retained under
`docs/evidence/issue-3844-fleet-discovery/`. Actual hosted conformance against the
live large repository remains a separate required gate after PR creation.
