# LangSmith Fleet Record Contract

`langsmith-fleet/v1` is the shared Workflows-owned contract for repo-emitted
LangSmith observability artifacts. Consumer repos own domain instrumentation;
Workflows owns the common record shape, registry, validation, and dashboard
status rollup.

## Design Decision

The fleet design is contract-first, not package-first:

- Workflows owns the canonical `langsmith-fleet/v1` record contract, JSON Schema,
  registry, validator, fixtures, and dashboard status rollup.
- Consumer repos own their local emitters, adapters, and domain instrumentation.
  They may implement local validation helpers as long as emitted
  `langsmith-fleet.ndjson` records conform to this contract and the registry's
  required domain fields.
- A consumer-local "subset" validator is not a design violation by itself. It is
  only incomplete if it allows records that fail the Workflows canonical schema,
  uses unsafe raw prompt/output payloads, misses registry-required domain fields,
  or emits unregistered repo/surface/operation combinations.
- Workflows does not currently publish a Python package for consumers to import.
  That design would only be worth changing to if the fleet starts seeing repeated
  schema drift, duplicated validator defects, or cross-repo release coordination
  failures that outweigh the packaging and version-management overhead.

Closer/verifier agents should consult this section before pausing for a human
decision about local validators. If the current repo artifacts conform to the
canonical schema and registry, advance or close the lane instead of halting on
implementation shape alone.

## Current Rollout State

The parent contract shipped through `stranske/Workflows#2150` /
`stranske/Workflows#2151`. The first fleet wave then implemented repo-local
emitters against the contract:

| Repo | Issue | Implementation PR | State |
| --- | --- | --- | --- |
| `stranske/Workflows` | `#2150` | `#2151` | Contract owner merged. |
| `stranske/Counter_Risk` | `#610` | `#629` | Repo-local emitter merged. |
| `stranske/Inv-Man-Intake` | `#438` | `#454` | Repo-local emitter merged; follow-up `#455` tracks contract-validation cleanup. |
| `stranske/Pension-Data` | `#445` | `#460`, `#461` | Repo-local emitter and trace-sink follow-up merged. |
| `stranske/trip-planner` | `#1208` | `#1226` | Repo-local emitter merged. |
| `stranske/Trend_Model_Project` | `#5311` | `#5328` | Repo-local emitter merged. |
| `stranske/Portable-Alpha-Extension-Model` | `#1802` | `#1819` | Repo-local emitter merged. |
| `stranske/Manager-Database` | `#1048` | `#1067` | Repo-local emitter merged. |

## Artifact

Each participating repo emits NDJSON at the artifact name registered in
`config/langsmith_fleet_registry.json` (default `langsmith-fleet.ndjson`). Each
line is one JSON object.

The artifact must be safe to publish in GitHub Actions artifacts and dashboards:
raw prompts, personal data, documents, SQL result rows, generated report text,
and full model outputs must be represented by hashes or artifact references.

## Shared Fields

Required fields:

| Field | Meaning |
| --- | --- |
| `schema_version` | Must be `langsmith-fleet/v1`. |
| `repo` | Full repository name, for example `stranske/trip-planner`. |
| `surface` | Registry surface name, for example `planner-runtime`. |
| `operation` | Repo-specific operation within the surface. |
| `run_id` | Stable run, session, package, request, or workflow identifier. |
| `status` | One of `success`, `error`, `fallback`, `no_secret`, or `skipped`. |
| `github_issue` | Owning implementation issue, for example `stranske/Workflows#2150`. |
| `domain` | Non-empty object with fields required by the registry entry. |

Optional shared fields:

| Field | Meaning |
| --- | --- |
| `trace_id` / `trace_url` | LangSmith trace reference when a key is configured. |
| `provider` / `model` | Model provider and model name. |
| `latency_ms` / `cost_usd` | Non-negative numeric measurements. |
| `input_hash` / `output_hash` | `sha256:`, `hash:`, `artifact:`, or `ref:` references only. |
| `github_pr` | PR that emitted or validates the record. |
| `recorded_at` | ISO timestamp used for stale-artifact detection. |
| `artifact_ref` | Pointer to a safe repo artifact. |
| `error_category` | Stable error/fallback category. |

## Registry

`config/langsmith_fleet_registry.json` maps each active repo issue to:

- repo, issue, and issue number,
- surface and allowed operation family,
- artifact name,
- rollout status,
- required domain fields.

Dashboard status is computed per registry entry:

- `missing`: no record was emitted for that repo/surface.
- `invalid`: records exist but fail the shared or domain-field contract.
- `stale`: latest valid record is older than the registry freshness window.
- `valid`: at least one current valid record exists.

## Validation

Run validation locally without a LangSmith key:

```bash
python scripts/langsmith_fleet.py tests/fixtures/langsmith_fleet/valid.ndjson
```

Render dashboard-ready status:

```bash
python scripts/langsmith_fleet.py tests/fixtures/langsmith_fleet/valid.ndjson \
  --summary --format markdown
```

The validator must fail malformed JSON, missing shared fields, unknown
repo/surface pairs, missing registry-required domain fields, unsafe raw
input/output payload fields, negative numeric measurements, and invalid statuses.
The canonical schema is versioned at
`docs/contracts/schemas/langsmith-fleet-v1.schema.json` and is enforced by
`scripts/langsmith_fleet.py`.

## Repo Responsibilities

Repo-specific issues should add instrumentation and emit compatible records.
They must not move domain tracing logic into Workflows. Workflows only validates
the emitted artifact and displays fleet status.
