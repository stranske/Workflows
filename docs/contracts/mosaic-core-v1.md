# Mosaic core v1

`mosaic-core/v1` carries one cross-source assertion or review record. Validate
against [mosaic-core-v1.schema.json](schemas/mosaic-core-v1.schema.json) with a
Draft 2020-12 validator and format checking enabled. `schema_version` is always
`mosaic-core/v1`; `record_type` selects exactly one subtype. Unknown additive
fields are allowed for v1 extensions. Unknown types, versions, and enum values
are rejected.

This is an interchange contract owned by Workflows. It introduces no database,
importer, entity-resolution service, or analyst UI. The four subtypes implement
the R3 manager-mosaic brief's Fact, Discrepancy, ThesisClaim, and ThesisCheck
records. Evidence remains the existing
[evidence-object/v1](schemas/evidence-object-v1.schema.json) contract.

## Record types

| `record_type` | Required subtype fields | Meaning |
| --- | --- | --- |
| `fact` | `fact_id`, `fact_key`, `entity_ref`, `value`, `status`, `primary_evidence_id` | A normalized assertion grounded in evidence. |
| `discrepancy` | `discrepancy_id`, `fact_key`, `entity_ref`, `fact_ids`, `discrepancy_kind`, `severity`, `status` | A reviewable conflict or a missing assertion. |
| `thesis_claim` | `thesis_id`, `claim_id`, `claim_text`, `entity_ref`, `fact_keys`, `evidence_policy` | An owner-written monitoring criterion. |
| `thesis_check` | `thesis_id`, `claim_id`, `verdict`, `evidence_ids`, `checked_at`, `trigger_source_id` | An attributable evaluation of a specific criterion. |

A Fact `value` is a JSON number, string, boolean, or numeric range object with
`min` and `max`. Null and arrays are not assertions. A producer normalizes units,
representation, and range ordering before export; consumers must also check
`min <= max`. JSON Schema validates structure, not cross-field arithmetic.
`status` is `asserted`, `superseded`, or `retracted`. `period` is optional; examples
are `2025-Q4` and `as_of:2025-12-31`. Generate `fact_id` deterministically from
`(fact_key, entity_ref, period, normalized_value)` using an unambiguous canonical
serialization. Consumers must not treat a changed value as the same fact.

A Discrepancy carries the same join coordinates, including optional `period`.
Its `fact_ids` are unique and nonempty. `numeric_delta`, `sign_conflict`, and
`narrative_conflict` require at least two competing facts; `missing_in_source`
may reference a single asserted fact. Severity is `low`, `normal`, or `high`;
thresholds belong to consumer comparison policy. Status is `open`,
`accepted_primary`, `immaterial`, or `resolved`. Every non-open status requires
a nonempty `resolution_note`. The schema does not authorize an actor to resolve
a conflict; analyst permissions remain consumer-owned. Generate a stable
`discrepancy_id` from the join coordinates.

A ThesisClaim groups `claim_id` under `thesis_id`, names nonempty unique
`fact_keys`, and selects `require_primary_source` or
`allow_marketing_only_with_flag`. Its optional `expected_pattern` is `min`,
`max`, `trend_up`, or `absent`; evaluation thresholds remain consumer policy.

A ThesisCheck identifies the same thesis and claim. Verdict is `supported`,
`at_risk`, `contradicted`, or `insufficient_evidence`. The first three require
at least one unique `evidence_id`; insufficient evidence permits an empty list.
`checked_at` is an RFC 3339 timestamp and `trigger_source_id` identifies the
incoming source that caused evaluation.

## Joining tracked variables and evidence

Copy `tracked-variable/v1.ontology_key` exactly to `Fact.fact_key`. Do not replace
it with the producer's `variable_id`, a display label, or a differently spelled
alias. Join on `(fact_key, entity_ref, period)` after explicit identity-alias and
period normalization. An absent period is not a wildcard. Two equal ontology
keys for different funds or periods are not a discrepancy pair.

For example, a tracked variable with `ontology_key: legal.management_fee.rate`
and `entity_ref: fund:synthetic_alpha` joins the synthetic fact fixture. The
Doc-Lineage `fact_key_map` artifact maps each `variable_id` to its original
`ontology_key` and `entity_ref`; it does not infer or silently rewrite identity.

`primary_evidence_id` and `evidence_ids` reference separately validated
`evidence-object/v1` records. Importers must verify reference existence, the
fact/claim associations, and primary-document locators. This single-record
schema cannot enforce cross-artifact referential integrity. Preserve evidence
`method`, a present `excerpt` (text or explicit null), and page locators for
paginated sources; an evidence ID alone is not proof of a navigable source.

## Manifest and delivery

`artifact-manifest/v1` adds `tracked_variables` and `mosaic_bundle` to its `kind`
enum. Existing kinds and path/hash rules are unchanged. A tracked-variable
artifact uses `tracked_variables`; a consumer-defined bundle containing these
records uses `mosaic_bundle`. This schema validates each contained record, not a
bundle container. The consumer owns its bundle layout and reference checks.

The schema and this specification are distributed from the Workflows root via
`.github/sync-manifest.yml` (`source_tree: root`), matching the existing backplane
contract delivery. No template-owned duplicate schema is maintained.

## Consumer validation

Declare `mosaic-core/v1` in an active consumer registry entry's `ingests` list
and pass one record to `scripts/validate_run_contract.py`. The production
validator checks all four record types and enforces `checked_at` date-time
format. Install `jsonschema` and `rfc3339-validator` when running it standalone;
`pip install -e ".[dev]"` and the reusable backplane conformance workflow include
both dependencies. The RFC 3339 checker is required, not an optional validation
step. Existing satellite schema validation behavior is unchanged.

## Workflows source validation evidence

The synthetic fixtures and tests below live in the
[Workflows source repository](https://github.com/stranske/Workflows), not in
consumer checkouts. From a Workflows checkout, run
`python -m pytest tests/contracts/test_backplane_schemas.py tests/contracts/test_validate_run_contract.py -q`; the named
acceptance gate is `test_mosaic_core_fixture_validates`. Negative tests exercise
discriminators, versions, empty join keys, evidence requirements, resolution
notes, and the additive manifest kinds with path rejection. Consumer-path tests
exercise the production validator for each fixture, a malformed Fact, and
invalid ThesisCheck timestamps.

Deliberate break: set `fact_key` to `""` in `valid_mosaic_fact.json`, run
`python -m pytest tests/contracts/test_backplane_schemas.py::test_mosaic_core_fixture_validates -q`,
observe failure, restore the fixture, and observe success. Record that transcript
in the implementation PR. `test_manifest_path_rejects_traversal` must also pass.
