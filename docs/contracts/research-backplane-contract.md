# Research Backplane Interoperability Contract

This document defines the **research-backplane interoperability program contract**
owned by Workflows. It is the ownership/program companion to the wire-format spec.

> **Status: P0 landing (under human review).** Opt-in and role-based. No
> participant emits or ingests an envelope yet; nothing here is wired into any
> repo's CI. This doc + the spec + schemas + registry + validator + reusable
> conformance workflow are the P0 contract set.

- Wire format (the run envelope): [`run-contract/v1`](./run-contract-v1.md).
- Satellite schemas:
  [`artifact-manifest-v1.schema.json`](./schemas/artifact-manifest-v1.schema.json),
  [`evidence-object-v1.schema.json`](./schemas/evidence-object-v1.schema.json).
- Identity conventions: [`identity-map-conventions.md`](./identity-map-conventions.md).
- Sibling observability contract (telemetry, not replay):
  [`langsmith-fleet/v1`](./langsmith-fleet-v1.md) /
  [`langsmith-observability-contract.md`](./langsmith-observability-contract.md).

It is modeled deliberately on the existing `langsmith-fleet/v1` program: Workflows
owns the contract, schema, registry, and validator; participating repos own their
local emitters/ingest adapters; the contract is **adopted, not imposed**.

## Ownership Boundary

Workflows owns:

- the shared `run-contract/v1` envelope contract and its JSON Schema,
- the satellite `artifact-manifest/v1` and `evidence-object/v1` schemas,
- the identity-map conventions (the canonical-ID string shape + source-of-truth
  rule),
- the opt-in participant registry (`config/backplane_participants.json`),
- the validator (`scripts/validate_run_contract.py`) and its fixtures,
- the reusable conformance workflow
  (`.github/workflows/reusable-backplane-conformance.yml`),
- the Workflows-internal contract-integrity gate
  (`.github/workflows/health-78-backplane-contract.yml`),
- reference-run / dashboard status rollup (`missing`/`invalid`/`stale`/`valid`).

Participating repos own:

- their domain compute and extraction logic (never moved into Workflows),
- their local emitter that projects existing run state into a conformant
  `run.json` (+ `manifest.json`), and/or their ingest adapter,
- their entity-resolution algorithm (for identity-authoritative repos).

## Reference-run artifact handoff

A participant caller emits its reference `run.json` and `manifest.json` in one
job, uploads them as the `reference-run` artifact, and then invokes the reusable
conformance workflow. The reusable workflow restores that artifact to
`artifacts/reference` before running the canonical validator. Callers that use
a different artifact name must pass it through `reference_artifact_name`. A
caller that intentionally has no emitted artifact remains an opt-in skip: the
restore failure is non-fatal and the validator decides whether that participant
is absent/planned or should fail for a missing required envelope.

## Roles: producer / consumer / bridge

Participation is **not binary in/out**. Each registry entry declares a `role`, and
the conformance gate validates the right surface for that role:

| `role` | Emits a `run.json`? | Ingests backplane artifacts? | What the gate checks |
| --- | --- | --- | --- |
| `producer` | Yes | (optionally) | Full `run-contract/v1` emission: all required shared fields + the entry's `required_sections`, plus the manifest cross-check. |
| `consumer` | No | Yes | **Only the schemas it ingests** (the satellite shapes named in `ingests`, e.g. `evidence-object/v1`, `artifact-manifest/v1`, identity refs). A consumer is never failed for not emitting a `run.json`. |
| `bridge` | Yes | Yes | Both the producer emission checks and the consumer ingest checks (the orchestrator/recipe step is the canonical bridge: it reads each step's `run.json` and emits a composite envelope). |

This is the load-bearing refinement over a "standardize every repo" model: a
downstream system can be a first-class participant **as a consumer** without being
forced to emit producer envelopes, and a recipe orchestrator is a **bridge**, not
a special case.

### Recommended first producers

The first producers are the investment research tools the feasibility memo scopes
in (see the registry for tiering and `status`):

- Tier 1: Pension-Data (reference tool / P2), Trend_Model_Project, Counter_Risk,
  Portable-Alpha-Extension-Model.
- Tier 2: Manager-Database (identity source), Inv-Man-Intake (evidence source).

All ship as `status: planned` in P0 — none emit yet.

### Cross-over consumers (architecture captured, not active)

The role model exists so cross-domain flows can be expressed *architecturally*
before they are built. The first such case is **investment-tool evidence/identity
flowing into a learning system**: `stranske/learning-management-system` is
recorded as a **`candidate` consumer** (not active). This documents that the LMS
*could* ingest backplane evidence objects / identity refs (e.g. to attribute a
learning artifact to a source document or a canonical entity) without:

- making LMS a producer (it emits no research run envelope), or
- conflating LMS's own domain contracts (`EvidenceRecord`/`MasteryEstimate`) with
  backplane evidence objects, or
- activating any gate (the gate skips `status: candidate` and `none` exactly like
  it skips an absent repo).

LMS stays in the `excluded` block as a **producer** (it is not a research tool),
*and* appears as a `candidate` **consumer** so a future reviewer sees the intended
architecture rather than an ambiguous absence. Flipping it from `candidate` to an
active `consumer` is a deliberate, reviewable charter decision — not something P0
does.

## Registry And Rollout Tracking

Every participant has a registry entry in `config/backplane_participants.json`
that defines: repo, parent implementation issue, `contract_version`, `role`,
`entry_point` (producers/bridges) or `ingests` (consumers), `artifact_name` /
`manifest_name`, `required_sections`, and `status`.

The registry is the **single central source of truth** and is read by the
reusable workflow from Workflows at run time. It is **not** synced to participants
(syncing it would create N drifting copies — the same discipline
`scripts/langsmith_fleet.py` applies to `config/langsmith_fleet_registry.json`).

`status` lifecycle: `planned` → `emitting` → `conformant`. `candidate` marks a
role-architecture placeholder that the gate treats as a no-op; `none`/absent means
the contract does not apply.

Excluded repos carry a `reason` so a future reviewer cannot mistake "absent" for
"forgotten" (the empty-signal anti-pattern). The four charter exclusions are
trip-planner, Travel-Plan-Permission, learning-management-system (as a producer),
and Workflows-as-an-application (it is the contract owner, mirroring
`langsmith-fleet`'s `rollout_status: contract-owner`).

## Validation Expectations

Validation must succeed offline (no cloud key), exactly like
`scripts/langsmith_fleet.py`.

The validator must **fail** (exit non-zero, `strict`):

- malformed/unloadable `run.json`,
- missing required shared fields or a wrong `schema_version`,
- a missing registry-required section (note `warnings`/`evidence_refs`/
  `identity_refs` are empty-OK; `cost`/`latency`/`data_quality` must be
  populated),
- any `outputs.artifact_ids` entry not present in the manifest with a `sha256`,
- a manifest that does not validate as `artifact-manifest/v1`,
- a non-canonical `identity_ref`,
- an inline raw payload (prompt/output/rows/PII) anywhere in the envelope,
- negative `cost`/`latency` numbers or an invalid `status`.

The one deliberate difference from the fleet validator: an **absent / `none` /
`candidate`** participant repo is a *skip* (opt-in respected), not a failure.

## Sync Story

Driven entirely through the existing `.github/sync-manifest.yml` — no new sync
machinery.

**Synced to participants** (so they can implement an emitter/ingest adapter and
validate locally): the spec (`run-contract-v1.md`), the three schemas, the
identity conventions, the validator (`scripts/validate_run_contract.py`), and the
templated caller stub
(`templates/consumer-repo/.github/workflows/backplane-conformance.yml`). The
reusable workflow body is referenced via `workflow_call@main`, so only the caller
stub is templated.

**Workflows-only** (referenced, not synced): the registry
(`config/backplane_participants.json`), this program doc, the internal
`health-78-backplane-contract.yml` gate, and the validator fixtures under
`tests/fixtures/backplane/`.

## Relationship to `langsmith-fleet/v1`

These are **sibling, complementary** contracts:

- `langsmith-fleet/v1` is *fleet observability telemetry* — one NDJSON line per
  operation, deliberately dropping inputs/outputs, for dashboard rollup.
- `run-contract/v1` is the *replayable per-run envelope* — one JSON object per
  run, carrying inputs/outputs/artifacts/evidence/cost/provenance so the run can
  be reproduced and diffed.

A strong participant emits both; the envelope's optional `langsmith` block links a
run to its trace so the two contracts cross-reference without duplicating
payloads.

## Repo Implementation Checklist

Each participant implementation issue (P1+) should:

1. Keep tool/compute/extraction logic in the participant repo, not in Workflows.
2. For a **producer/bridge**: emit a `run.json` (+ `manifest.json`) that validates
   as `run-contract/v1` (+ `artifact-manifest/v1`). For a **consumer**: validate
   the satellite schemas it ingests.
3. Populate shared fields exactly as the registry entry defines.
4. Populate the optional sections its registry entry lists in
   `required_sections`.
5. Avoid raw prompts/output/PII; publish references, hashes, and bounded
   excerpts.
6. Link back to the parent Workflows backplane issue so rollout status is tracked
   centrally; cross-link the `langsmith` trace where present.
