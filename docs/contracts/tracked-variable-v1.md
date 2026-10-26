# Research Backplane Tracked Variable Contract

`tracked-variable/v1` is the shared Workflows-owned contract for **asserted claims**
extracted from source documents — legal clauses, consultant report sections, and
thesis monitoring claims share one wire shape; vocabulary files differ by
`ontology_family` only.

> **Status: P0 landing (under human review).** Schema:
> [`tracked-variable-v1.schema.json`](./schemas/tracked-variable-v1.schema.json).
> Program context: [`research-backplane-contract.md`](https://github.com/stranske/Workflows/blob/main/docs/contracts/research-backplane-contract.md) (Workflows-only; deliberately not synced to consumers).
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

## Extraction coverage

Doc-Lineage's domain extractor `extract-variables` currently requests only
`legal.fees.management_rate`, loaded from the legal vocabulary. It reads a
persisted ingest run and requires the original document (`--source`) and a
caller-supplied canonical `--entity-ref`. It does not infer fund identity or
resolve aliases. Use an ID from your identity authority; syntax validation is
not proof that the ID identifies the right entity.

Supported English clause forms (case insensitive, normalized spaces) are exactly:

- `The Partnership shall pay the General Partner an annual management fee equal to X% of aggregate Capital Commitments.`
- The same sentence with ` during the Commitment Period, and Y% of invested capital thereafter.` replacing its final period.

An optional numbered `N. MANAGEMENT FEE ` heading is accepted. X and Y are
literal percentages between 0 and 100 inclusive, with at most four decimal places.
`value_structured.unit` is `percent_per_annum`, **not** a fractional rate. The
`schedule` retains each rate, basis and period: `Commitment Period`/`thereafter`
for the two-tier form and `all` for the flat form. `value_text` preserves the
clause substring. No rate is selected by position from unrelated percentages.

Offline ingest can place several sections in one page segment. Only numbered
uppercase headings delimit sections. Text before the fee section in that segment
must be empty or an LPA title of the form `[SYNTHETIC ]LIMITED PARTNERSHIP AGREEMENT
<Name> L.P.` (one to twelve capitalized name tokens, with spaces/commas). An
unrecognized preamble is unresolved. The complete original segment quote must
fit in the ingest evidence excerpt; truncated quotes cannot support an assertion.
These limits intentionally leave other layouts and wording unresolved.

Ranges, conditional/qualified language, competing fee candidates, missing fee
text and incomplete ingest coverage yield **no asserted record** and an entry
in `unresolved.json` with a reason and any candidate evidence references. An
unresolved entry has no asserted value and is not a `tracked-variable/v1` claim.
Other ontology keys are outside this initial coverage; their absence is not a
finding that those clauses do not exist. This is a bounded text grammar, not
arbitrary legal interpretation or a guarantee of document-wide legal consistency.

Each assertion embeds the unchanged ingest evidence object and references its
copied file. Its `fact_ref` continues to identify the source segment.
`document_id` is `document:<original SHA-256>`; `variable_id` hashes the original
digest, caller entity ID, ontology key and segment ID. It is stable on replay and
changes with source bytes or entity identity. No reporting period is inferred.
Evidence/document locators use **zero-based** pages; the mirror `#page=N` link
uses the PDF viewer's **one-based** physical page. The mirror anchor points to a
byte-identical original document copied into the new extraction directory.

Before creating output, the extractor validates the manifest, every listed
artifact's hash and size, segment identities/counts, every evidence object and
its exact segment/source/page link, and each asserted record against the shared
schemas. Missing, corrupted, duplicated or mismatched provenance fails closed;
it is an error, not an unresolved legal judgment. Schema references resolve
locally. Publication includes `tracked-variables.json`, `unresolved.json`, the
original source, segments, evidence and `input-manifest.json`, all hash-bound by
a new manifest. Extraction output directories must be new; ingest input is read-only. These checks establish
consistency with the supplied ingest run and original document digest; they do
not authenticate a maliciously rewritten, internally consistent ingest package.

```bash
doc-lineage ingest tests/fixtures/synthetic_lpa.pdf --no-docling --no-ocr --output ingest-run
doc-lineage extract-variables ingest-run --source tests/fixtures/synthetic_lpa.pdf \
  --entity-ref fund:alpha_opportunities_iv --output extraction-run
doc-lineage export-fact-key-map extraction-run/tracked-variables.json --output fact-map-run
```

Inspect `extraction-run/unresolved.json` before consuming claims. A successful
extraction command can publish an entirely unresolved run; the fact-map exporter
requires at least one asserted record and therefore rejects an empty array.
