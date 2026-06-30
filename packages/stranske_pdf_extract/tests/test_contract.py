"""Contract validators + evidence-ref identity (deterministic, no deps)."""

from __future__ import annotations

import pytest
from stranske_pdf_extract.contract import (
    EvidenceRef,
    ExtractedDocumentResult,
    ExtractedField,
    ProviderExtractionOutput,
    SourceLocation,
    validate_extracted_document_result,
    validate_provider_output,
)


def _field(**kw) -> ExtractedField:
    base = {
        "key": "nav",
        "value": "100.0",
        "confidence": 0.9,
        "source_doc_id": "doc1",
        "source_page": 1,
        "method": "table",
    }
    base.update(kw)
    return ExtractedField(**base)


def test_evidence_ref_canonical_forms():
    assert EvidenceRef("doc1", page_number=40).canonical == "doc1#page=40"
    assert EvidenceRef("doc1", snippet_anchor="nav").canonical == "doc1#anchor=nav"
    assert EvidenceRef("doc1", section_hint="summary").canonical == "doc1#section=summary"
    assert EvidenceRef("doc1").canonical == "doc1"


def test_evidence_ref_id_excludes_enrichment():
    # Enriching a locator with method/excerpt must NOT change its stable identity.
    bare = EvidenceRef("doc1", page_number=40)
    enriched = EvidenceRef("doc1", page_number=40, method="table", excerpt="Funded ratio 84%")
    assert bare.ref_id == enriched.ref_id
    # A different locator gets a different id.
    assert EvidenceRef("doc1", page_number=41).ref_id != bare.ref_id


def test_validate_good_result_passes():
    result = ExtractedDocumentResult(
        source_doc_id="doc1", provider_name="text_baseline", fields=(_field(),)
    )
    validate_extracted_document_result(result)  # no raise


@pytest.mark.parametrize(
    "bad",
    [
        _field(value=""),
        _field(confidence=1.5),
        _field(method="   "),
        _field(source_doc_id="other"),
        _field(source_page=-1),
    ],
)
def test_validate_rejects_bad_fields(bad):
    result = ExtractedDocumentResult(source_doc_id="doc1", provider_name="p", fields=(bad,))
    with pytest.raises(ValueError):
        validate_extracted_document_result(result)


def test_strict_evidence_requires_ref_for_high_impact_fields():
    funded = _field(key="funded_ratio", value="0.84")
    result = ExtractedDocumentResult(source_doc_id="doc1", provider_name="p", fields=(funded,))
    # Lenient mode tolerates the missing ref...
    validate_extracted_document_result(result)
    # ...strict mode requires it.
    with pytest.raises(ValueError, match="high-impact"):
        validate_extracted_document_result(result, strict_evidence=True)
    # Supplying the evidence ref satisfies strict mode.
    ok = ExtractedDocumentResult(
        source_doc_id="doc1",
        provider_name="p",
        fields=(
            _field(key="funded_ratio", value="0.84", evidence=EvidenceRef("doc1", page_number=40)),
        ),
    )
    validate_extracted_document_result(ok, strict_evidence=True)


def test_evidence_ref_must_match_result_document():
    result = ExtractedDocumentResult(
        source_doc_id="doc1",
        provider_name="p",
        fields=(
            _field(
                key="funded_ratio",
                value="0.84",
                evidence=EvidenceRef("other-doc", page_number=40),
            ),
        ),
    )
    with pytest.raises(ValueError, match="EvidenceRef.source_doc_id"):
        validate_extracted_document_result(result, strict_evidence=True)


def test_evidence_ref_page_number_must_be_positive():
    result = ExtractedDocumentResult(
        source_doc_id="doc1",
        provider_name="p",
        fields=(
            _field(
                key="funded_ratio",
                value="0.84",
                evidence=EvidenceRef("doc1", page_number=0),
            ),
        ),
    )
    with pytest.raises(ValueError, match="page_number"):
        validate_extracted_document_result(result, strict_evidence=True)


def test_validate_provider_output_checks_locations():
    bad = ProviderExtractionOutput(
        source_doc_id="doc1",
        provider_name="p",
        text_blocks=(),
    )
    validate_provider_output(bad)  # empty is valid
    # SourceLocation doc id must match the output doc id.
    loc = SourceLocation(source_doc_id="WRONG", source_page=1)
    from stranske_pdf_extract.contract import ExtractedImage

    with pytest.raises(ValueError):
        validate_provider_output(
            ProviderExtractionOutput(
                source_doc_id="doc1", provider_name="p", images=(ExtractedImage(location=loc),)
            )
        )
