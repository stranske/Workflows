# Document Identity Conventions

This is a fleet contract for document identity and source attribution. Workflows
owns the convention and schema; Doc-Lineage, Deliverable-Render, Inv-Man-Intake,
and Pension-Data resolve documents in their own corpora. There is no central
resolver or shared Python package.

## Content-first identity

The primary document ID is the lowercase SHA-256 digest of the document's
original bytes. A rename or move preserves this ID. A byte change creates a new
ID, even when the title and date are unchanged. Keep the original bytes or a
verifiable digest alongside any OCR or normalized text projection.

`doc_key` is a human-readable secondary index, formed as
`{entity_ref}/{doc_type}/{as_of}`. The entity reference follows
[`identity-map-conventions.md`](identity-map-conventions.md); `as_of` is an ISO
date when known, or `unknown`. **`doc_key` is not unique**: separate byte
versions can share one key. Neither a path nor a filename is an identity key.

The closed `doc_type` vocabulary is `call_note`, `manager_letter`,
`data_packet`, `legal_document`, `consultant_report`, `research_article`,
`marketing_material`, `regulatory_filing`, `audited_financial_statement`,
`questionnaire`, `internal_diligence_report`, and `presentation`. Adding a
member is additive; removing or reinterpreting one requires a versioned
contract change.

## Supersession

`supersedes` names the earlier document's SHA-256 ID, and must be paired with
`supersession_evidence`. Its `mechanism` is `source_metadata`,
`content_comparison`, or `owner_assertion`; `detail` records the specific
version notice, comparison, or dated assertion. Matching titles, paths, or
numeric filename prefixes alone do not prove supersession. Corpus owners
resolve disputes and preserve both byte versions.

## Evidence references and text basis

An `evidence-object/v1` may carry `document_ref` with `sha256`, `doc_key`,
`doc_type`, and `text_basis`. `text_basis` is `native`, `ocr`, `mixed`, or
`unknown`. Use `unknown` when the extraction method cannot be established;
never silently assume `native`. A nonempty `excerpt` is a quote and requires
`document_ref.page`, zero-based to match the existing `locator.page`. If both
pages are present they must agree.

Set `evidence_kind` to `document_text_coverage` for a coverage or completeness
figure derived from document text. This requires `document_ref` and therefore
an explicit `text_basis`. The figure remains in the fact or metric identified
by `fact_ref`; the evidence object identifies the source and extraction basis.
Describe the denominator and calculation scope in the producing repo's metric
contract so OCR gaps are not mistaken for complete source coverage.

Evidence objects without `document_ref` remain valid for existing participants.
Adoption is additive and belongs in each corpus-owning repo.
