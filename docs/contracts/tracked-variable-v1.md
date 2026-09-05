# Research Backplane Tracked Variable Contract

`tracked-variable/v1` is the shared Workflows-owned contract for **asserted claims**
extracted from source documents — legal clauses, consultant report sections, and
thesis monitoring claims share one wire shape; vocabulary files differ by
`ontology_family` only.

> **Status: P0 landing (under human review).** Schema:
> [`tracked-variable-v1.schema.json`](./schemas/tracked-variable-v1.schema.json).
> Program context: [`research-backplane-contract.md`](./research-backplane-contract.md).
> Embedded evidence: [`evidence-object-v1.schema.json`](./schemas/evidence-object-v1.schema.json).

## Design Decision

R1 (legal clauses), R2 (consultant sections), and R3 (thesis monitoring) converge
on the same unit: an asserted claim with ontology key, typed value, evidence, and
supersession. Workflows owns the schema and validator; domain repos own vocabulary
data and extractors.

- Every `tracked-variable/v1` object **must** carry an embedded `evidence` object
  conforming to [`evidence-object/v1`](./schemas/evidence-object-v1.schema.json)
  (required `method` and `excerpt`).
- Every object **must** carry dual provenance anchors:
  `provenance.document` (primary page navigation) and `provenance.mirror` (local
  offline blob path). See B3 interop architecture §3.1.
- Workflows syncs the schema and normative spec; domain repos sync vocabulary
  artifacts, not judgment.

## Required Fields

| Field | Requirement |
| --- | --- |
| `schema_version` | Must be the literal `tracked-variable/v1`. |
| `evidence` | **Required.** Embedded [`evidence-object/v1`](./schemas/evidence-object-v1.schema.json) with `method` and `excerpt` present. |
| `provenance` | **Required** object with both `document` and `mirror` sub-objects. |
| `provenance.document` | Primary source anchor (`source_id`, optional `locator.page` for PDFs). |
| `provenance.mirror` | Local mirror anchor (`mirror_root`, `blob_path`, `page_anchor`). |

All other fields in the B3 §3.1 sketch (`variable_id`, `ontology_key`,
`ontology_family`, `value_text`, `entity_ref`, etc.) are defined by the schema but
may be populated as extractors mature.

## Clause Variable Alias

`clause-variable/v1` is a **vocabulary alias**, not a separate schema. Emitters that
produce legal-clause extractions use the same `tracked-variable/v1` wire shape with:

```json
{
  "schema_version": "tracked-variable/v1",
  "ontology_family": "clause",
  "ontology_key": "legal.withdrawal.notice_days"
}
```

The alias name (`clause-variable/v1`) appears in vocabulary and ingest documentation
only; on the wire the `schema_version` remains `tracked-variable/v1`. Vocabulary
for `ontology_family: "clause"` is owned by Doc-Lineage (`vocab/legal-clauses.json`).

Equivalent aliases for other families:

| Alias (documentation) | `ontology_family` | Vocabulary owner |
| --- | --- | --- |
| `clause-variable/v1` | `"clause"` | Doc-Lineage |
| (report sections) | `"report_section"` | Doc-Lineage + Inv-Man-Intake |
| (thesis claims) | `"thesis_claim"` | Per-workspace `thesis-vocabulary.json` |

## Validation

Offline validation:

```bash
python scripts/validate_run_contract.py \
  --tracked-variables tests/fixtures/backplane/valid_tracked_variable.json \
  --schema-dir docs/contracts/schemas
```

Contract tests:

```bash
python -m pytest tests/contracts/test_backplane_schemas.py::test_tracked_variable_fixture_validates -q
```
