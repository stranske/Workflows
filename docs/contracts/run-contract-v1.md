# Research Backplane Run Contract

`run-contract/v1` is the shared Workflows-owned contract for repo-emitted
**run envelopes** on the investment research backplane. Participating tools own
their domain compute and instrumentation; Workflows owns the common run-record
shape, the participant registry, validation, and the cross-repo reference-run
rollup.

> **Status: P0 landing (under human review).** This is the wire-format spec.
> Schema: [`run-contract-v1.schema.json`](./schemas/run-contract-v1.schema.json).
> Program/ownership doc: [`research-backplane-contract.md`](./research-backplane-contract.md).
> Sibling observability contract: [`langsmith-fleet-v1.md`](./langsmith-fleet-v1.md).
> The contract is **opt-in**: a repo participates only via an entry in
> `config/backplane_participants.json`. No participant emits an envelope yet
> (that is P1+); nothing here is wired into any repo's CI.

## Design Decision

The run contract is contract-first, not package-first, and opt-in, not
fleet-wide (same stance as `langsmith-fleet/v1`):

- Workflows owns the canonical `run-contract/v1` envelope, its JSON Schema, the
  `artifact-manifest/v1` and `evidence-object/v1` satellite schemas, the
  identity-map conventions, the registry (`config/backplane_participants.json`),
  the validator (`scripts/validate_run_contract.py`), fixtures, and the
  reusable conformance workflow.
- Participating repos own their local emitters and adapters. They project their
  existing run state (`RunResult`, ledgers, `manifest.json`) into a conformant
  `run.json`. A consumer-local helper is fine as long as the emitted envelope
  conforms to this contract and the registry's participant requirements.
- A consumer-local subset validator is not a design violation by itself. It is
  only incomplete if it allows envelopes that fail the Workflows canonical
  schema, references artifacts not present in the manifest, drops a
  registry-required section, emits non-canonical identity refs, or carries
  unsafe raw input/output payloads.
- Workflows does not currently publish a Python package for participants to
  import. That would only be worth the version-management overhead if the
  backplane starts seeing repeated schema drift, duplicated validator defects,
  or cross-repo release-coordination failures.

Orchestrator/verifier agents should consult this section before pausing for a
human decision about local emitters. If the current repo artifacts conform to
the canonical schema and registry, advance the recipe instead of halting on
implementation shape alone.

## Why this contract exists (the keystone gap)

Across the six investment repos, `run_contract` scores **uniformly 2/3 (one
outlier at 1/3)**, and the gap is identical everywhere: **there is no single JSON
object representing a whole run** with who/why + validated inputs + outputs +
named artifacts + warnings + cost/latency + provenance, replayable as one record
(`FEASIBILITY-blueprint.md` §4.1). The pieces exist but are split across
in-memory dataclasses, a fleet-telemetry NDJSON, and separate manifests:

- Trend_Model: data split across in-memory `RunResult` (holds DataFrames, not
  JSON-serializable), `run_meta.json`, and `manifest.json`; no cost/latency on
  the run path; warnings only via `logging` (`api.py:604`); no actor/intent.
- PAEM: provenance split across `manifest.json`, `run_end.json`, `bundle.json`;
  **warnings never serialized** (only stderr); **no cost** (`contracts.py:136`
  `ManifestPayload` has neither).
- Pension-Data: orchestration has a ledger, but the NL/SQL surface persists
  nothing beyond an in-memory audit row; **cost captured nowhere** (grep for
  `cost_usd|tokens` is empty).
- Counter_Risk: schema'd manifest exists but has **no top-level
  `schema_version`, no actor/why, no cost**; the full `manifest_schema()` is
  never enforced against a written manifest.
- Manager-Database (1/3): core tools return bare `list`/`None`; `cost_usd`
  hard-coded `0.0` (`adapters/base.py:173`).
- Inv-Man-Intake: full run is a `V1SmokeArtifacts` dataclass of `object` fields,
  never serialized to one envelope.

`run-contract/v1` is that single object. It is **additive**: a participant keeps
its existing `RunResult`/manifests and adds the envelope as an export-time
projection.

## Artifact

Each participating repo emits one JSON object per run at the artifact name
registered in `config/backplane_participants.json` (default `run.json`), written
under a per-run directory using the convention
`artifacts/<tool>/<run_id>/run.json` (the layout Manager-Database's blueprint
already proposes; `FEASIBILITY-blueprint.md` §5 Phase 1).

The envelope must be safe to publish in GitHub Actions artifacts and dashboards:
**raw prompts, personal data, documents, SQL result rows, generated report text,
and full model outputs must be represented by hashes, excerpts of bounded
length, or artifact references** — never inlined. Output *data* lives in named
artifacts referenced by the manifest, not in the envelope body.

## Shared Fields

Required fields:

| Field | Meaning |
| --- | --- |
| `schema_version` | Must be `run-contract/v1`. |
| `repo` | Full repository name, for example `stranske/Pension-Data`. |
| `tool` | Stable tool identifier within the repo, for example `nl-to-sql` or `run-simulation`. Matches a registry `entry_point` tool. |
| `run_id` | Stable run identifier. SHOULD be content-addressed (e.g. `sha256(inputs|config|seed)`) so replays and "already-done" detection work; MUST be stable across a deterministic re-run. |
| `status` | One of `success`, `error`, `partial`, `fallback`, `skipped`. |
| `actor` | Who/why object: who initiated the run and why (see below). |
| `inputs` | Validated input echo / references (see below). Never raw payloads. |
| `outputs` | Output summary + the manifest reference (see below). |
| `provenance` | Tool + code + environment provenance (see below). |
| `github_issue` | Owning implementation issue, for example `stranske/Workflows#<n>`. |

### `actor` (who/why)

| Subfield | Req | Meaning |
| --- | --- | --- |
| `actor.kind` | required | `human`, `agent`, `schedule`, `recipe`, or `ci`. |
| `actor.id` | required | Caller key, agent key, recipe id, or schedule id. Not PII; use a key/handle, not a name+email. |
| `actor.intent` | optional | Short free-text or coded reason ("weekly counterparty refresh", recipe step id). The "why". |
| `actor.correlation_id` | optional | Ties this run to an orchestrator/recipe run or an upstream request. |

This closes the fleet-wide "no who/why" gap (every repo lacks an actor/intent
field; `FEASIBILITY-blueprint.md` §4.1).

### `inputs` (validated, never raw)

| Subfield | Req | Meaning |
| --- | --- | --- |
| `inputs.validated` | required | `true` once the tool has validated inputs against its own schema/Pydantic model before running. |
| `inputs.refs` | optional | List of `input_hash`-style references (`sha256:`/`artifact:`/`ref:`) to input files (e.g. `config_sha256`, `input_sha256`). |
| `inputs.summary` | optional | A bounded, safe summary object (e.g. `{ "as_of_date": "...", "scenario": "..." }`) — domain keys, no raw rows/PII. |

### `outputs`

| Subfield | Req | Meaning |
| --- | --- | --- |
| `outputs.manifest_ref` | required | Reference to the run's `artifact-manifest/v1` manifest (`artifact:manifest.json` or a relative path). The named artifacts live there, not inline. |
| `outputs.summary` | optional | Bounded safe summary of results (e.g. `{ "final_score": 0.7809 }`, `{ "limit_breach_count": 0 }`). No raw rows / full text. |
| `outputs.artifact_ids` | optional | The stable `artifact_id`s (from the manifest) this run produced, for quick orchestrator threading. |

### `provenance`

| Subfield | Req | Meaning |
| --- | --- | --- |
| `provenance.tool_version` | required | The producing package version (`importlib.metadata.version` / `VERSION`). |
| `provenance.git_sha` | optional | Best-effort git SHA; `null` when unavailable. |
| `provenance.python_version` | optional | Interpreter version. |
| `provenance.platform` | optional | OS/platform string. |
| `provenance.code_version` | optional | Any additional code-identity hash the tool already computes (PAEM has one). |

This closes the Counter_Risk/Trend_Model provenance gap (tool+git+python version
needed for replay/audit; `Counter_Risk` blueprint issue, `manifest.py:97-120`).

## Optional Shared Fields

| Field | Meaning |
| --- | --- |
| `cost` | Object: `{ "usd": number\|null, "input_tokens": int, "output_tokens": int }`. `usd` is null-able for non-LLM/local-numpy runs; **the point is the field exists** so cost stops being un-capturable (the universal gap: cost is captured nowhere in ≥3 repos, hard-coded `0.0` in Manager-Database `adapters/base.py:173`). |
| `latency` | Object: `{ "wall_ms": number }` (+ optional `peak_mem_mb`). Most repos already have a timing value; this normalizes it into the envelope. |
| `warnings` | Array of `{ "code", "severity", "message", "context"? }`. Closes the universal "warnings survive only to logs/stderr" gap (PAEM, Trend_Model, Counter_Risk). Severity ∈ `info`/`warning`/`error`. When a tool's registry entry lists `warnings` as required, the *key* must be present; an **empty array is valid** and means "ran, no warnings" (a clean run is not a contract violation). |
| `data_quality` | Object surfacing run-level missingness/conflict/low-confidence state (counts of dropped/coerced rows, a `conflict` indicator when two sources disagree). Closes the "rich at the domain layer, collapsed at the run layer" gap (`FEASIBILITY-blueprint.md` §4.5). Optional and only meaningful for tools whose registry entry lists `data_quality` in `required_sections`. |
| `evidence_refs` | Array of references to `evidence-object/v1` objects (by `evidence_id`), present when the tool's run produced attributable facts. See `schemas/evidence-object-v1.schema.json`. Required-when-applicable per the registry's `required_sections`. |
| `identity_refs` | Array of canonical entity IDs (per `identity-map-conventions.md`) this run consumed/emitted, so the orchestrator can join across tools. |
| `langsmith` | Object: `{ "trace_id", "trace_url" }` linking this run to its `langsmith-fleet/v1` trace. Cross-references the sibling observability contract without duplicating payloads. |
| `recorded_at` | ISO timestamp used for stale-artifact / reference-run freshness. |
| `parent_run_id` | When this run is a step inside a recipe, the orchestrator's composite `run_id`. |

## Registry

`config/backplane_participants.json` maps each opted-in repo to:

- repo and parent implementation issue,
- adopted `contract_version` (`run-contract/v1`),
- a `role` — `producer` | `consumer` | `bridge` (see below),
- declared headless `entry_point` (the tool's invocation contract),
- `artifact_name` (default `run.json`) and `manifest_name` (default
  `manifest.json`),
- `required_sections` — which optional sections are mandatory *for this tool*
  (e.g. an extraction tool requires `evidence` + `identity`; a Monte Carlo
  engine requires neither),
- `status` (`planned` → `emitting` → `conformant`; or `candidate` for a
  pre-approval role-architecture placeholder that the gate treats as a no-op).

### Participant `role` (producer / consumer / bridge)

Participation is **not binary in/out**. Each participant declares a `role` so the
conformance gate validates the right thing for it:

- **`producer`** — a research tool that *emits* a full `run-contract/v1` envelope
  (+ `artifact-manifest/v1` manifest) from its run. The recommended first
  producers are the Tier-1/Tier-2 investment tools. A producer's gate validates
  full run-contract emission (all required shared fields + its
  `required_sections`).
- **`consumer`** — a downstream system that *ingests* backplane artifacts
  (e.g. evidence objects and identity refs) but does not itself run a research
  tool that emits a run envelope. A consumer's gate validates **only the schemas
  it ingests** (the satellite `evidence-object/v1` / `artifact-manifest/v1`
  shapes named in its `ingests`), **not** full producer run-contract emission. A
  consumer is never failed for not emitting a `run.json`.
- **`bridge`** — a participant that both ingests upstream artifacts and emits its
  own envelope (an orchestrator/recipe step is the canonical bridge: it reads
  each step's `run.json` and emits a composite one). A bridge's gate applies both
  the producer emission checks and the consumer ingest checks.

This role model is what lets cross-over use cases be expressed *architecturally*
without forcing them live: e.g. investment-tool evidence/identity flowing into a
learning system is a `consumer` relationship, recorded as a `candidate` entry so
the architecture is captured while the consumer stays inactive (the gate skips
`candidate`/`none`). See `research-backplane-contract.md` for the
producer/consumer/bridge ownership boundaries.

Reference-run / dashboard status is computed per participant entry, mirroring the
fleet `missing`/`invalid`/`stale`/`valid` rollup:

- `missing`: no `run.json` was emitted for that participant's reference run.
- `invalid`: a `run.json` exists but fails the shared schema or a
  registry-required section.
- `stale`: latest valid envelope is older than the registry freshness window.
- `valid`: at least one current valid envelope exists.

## Validation

Run validation locally without any cloud key (deterministic, offline — the same
guarantee as `langsmith_fleet.py`):

```bash
python scripts/validate_run_contract.py tests/fixtures/backplane/valid_run.json
```

Validate against a specific participant's registry requirements and its manifest:

```bash
python scripts/validate_run_contract.py \
  artifacts/pension-data/<run_id>/run.json \
  --manifest artifacts/pension-data/<run_id>/manifest.json \
  --repo stranske/Pension-Data
```

The validator must fail: malformed JSON, missing required shared fields, an
unknown/absent participant repo, missing registry-required sections (e.g.
`evidence_refs` absent when the entry requires `evidence`), any artifact named in
`outputs.artifact_ids` that is not present in the manifest with a `sha256`,
non-canonical identity refs, unsafe raw input/output payload fields, negative
`cost`/`latency` numbers, and invalid `status` values. The canonical schema is
versioned at `docs/contracts/schemas/run-contract-v1.schema.json` and is enforced
by `scripts/validate_run_contract.py`.

## Repo Responsibilities

Participant implementation issues add an emitter and emit a conformant envelope.
They must **not** move domain compute or extraction logic into Workflows.
Workflows only validates the emitted envelope/manifest and rolls up reference-run
status.

Each participant implementation issue should:

1. Keep tool/compute/extraction logic in the participant repo, not in Workflows.
2. Emit a `run.json` (+ `manifest.json`) that validates as `run-contract/v1`
   (+ `artifact-manifest/v1`).
3. Populate shared fields (`repo`, `tool`, `run_id`, `status`, `actor`,
   `inputs`, `outputs`, `provenance`, `github_issue`) exactly as the registry
   entry defines.
4. Populate the optional sections its registry entry lists in
   `required_sections` (e.g. `cost`, `warnings`, `evidence_refs`,
   `identity_refs`).
5. Avoid raw prompts/output/PII; publish references, hashes, and bounded
   excerpts instead.
6. Link back to the parent Workflows backplane issue so rollout status is
   tracked centrally, and (where present) cross-link the `langsmith` trace.
