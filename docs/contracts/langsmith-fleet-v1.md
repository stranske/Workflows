# LangSmith Fleet Record Contract

`langsmith-fleet/v1` is the shared Workflows-owned contract for repo-emitted
LangSmith observability artifacts. Consumer repos own domain instrumentation;
Workflows owns the common record shape, registry, validation, and dashboard
status rollup.

## Design Decision

The fleet design is contract-first, not package-first. It also distinguishes
how coverage is proved from whether LangSmith is applicable at all:

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
- `artifact` registry entries prove coverage with a repo-local
  `langsmith-fleet.ndjson` artifact.
- `langsmith-direct` registry entries prove agent-automation tracing through the
  Workflows-owned direct integration and do not emit a repo-local artifact.
- Repositories in `config/langsmith_fleet_allowlist.json` are explicitly
  `not-applicable`: they receive shared maintenance updates, but have no
  substantive runtime whose LangSmith coverage could be measured.

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
| `stranske/Travel-Plan-Permission` | `#1238` | `#2487` (registry) | Covered by Workflows-owned direct agent tracing; no repo-local artifact expected. |
| `stranske/learning-management-system` | `#334` | `#2487` (registry) | Covered by Workflows-owned direct agent tracing; no repo-local artifact expected. |
| `stranske/Fine-Art-Archive` | `#114` | `#2487` (registry) | Covered by Workflows-owned direct agent tracing; no repo-local artifact expected. |

## Artifact

Each `evidence_mode=artifact` repo emits NDJSON at the artifact name registered
in `config/langsmith_fleet_registry.json` (default
`langsmith-fleet.ndjson`). Each line is one JSON object. Direct-evidence and
not-applicable repositories do not emit this artifact.

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

### Workflows-Owned Automation Evidence

The `stranske/Workflows` / `agent-automation` surface may also emit
`operation=durability` records for recently merged `agents:keepalive` PRs. These
records use `github_pr` to point at the consumer PR being classified and keep
consumer-specific details in `domain.target_repo`, `domain.target_pr`, and
`domain.durability`. They are post-merge learning evidence only; they must not
block or reopen the original merge path.

## Registry

`config/langsmith_fleet_registry.json` maps each active repo issue to:

- repo, issue, and issue number,
- surface and allowed operation family,
- artifact name,
- evidence mode (`artifact` or `langsmith-direct`),
- rollout status,
- required domain fields.

`config/langsmith_fleet_allowlist.json` covers registered maintenance consumers
where runtime observability is intentionally not applicable. The current
allowlist is Template, Ready, and Collab-Admin. A repository created from one
of those templates must move into the registry when it gains a substantive
runtime; that activation condition is recorded in each allowlist entry and is
validated alongside Maint 68 consumer coverage.

Dashboard status is computed per registry entry:

- `missing`: no record was emitted for that repo/surface.
- `invalid`: records exist but fail the shared or domain-field contract.
- `stale`: latest valid record is older than the registry freshness window.
- `valid`: at least one current valid record exists.
- `direct`: coverage uses Workflows-owned direct LangSmith tracing, so no
  repo-local artifact is expected.
- `not-applicable`: the repository is an explicitly allowlisted maintenance
  consumer without a substantive runtime.

`missing`, `invalid`, and `stale` apply only to artifact-backed entries. A
missing artifact means the GitHub dashboard cannot prove current coverage; it
does not, by itself, prove that LangSmith tracing failed. Conversely, a direct
entry proves the configured integration path, not live per-repo trace success;
live direct-trace health must be reported by the Workflows automation telemetry
surface.

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

Artifact-backed repo issues should add instrumentation and emit compatible records.
They must not move domain tracing logic into Workflows. Workflows only validates
the emitted artifact and displays fleet status. Direct-evidence repos rely on
the Workflows-owned agent tracing path, while allowlisted repos must be promoted
to the registry as soon as substantive runtime behavior is introduced.
