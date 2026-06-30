"""The single result + page-level-provenance contract for fleet PDF extraction.

This generalizes the two most mature fleet contracts so each consumer keeps the
other's strengths (see ``docs/DESIGN.md`` §1.1):

* **Inv-Man-Intake** contributed the modality-grouped raw output and ``SourceLocation``
  with **bbox** + char-offset provenance (the superset locator) and runtime-checkable
  validators.
* **Pension-Data** contributed the evidence-ref canonicalization, the ``ExtractionMethod``
  enum, stable content-hashed ids (enrichment never changes identity), and per-link
  confidence used for citation export.

Everything here is pure-Python and deterministic. Domain field schemas stay in the
consumer; this module only models *where a value came from* and *how confident we are*.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

# Extraction path that produced a value. Superset of Pension-Data's `method` enum
# ("table"|"text"|"fallback"|"ocr"|"llm") extended with the methodology doc's vision path.
ExtractionMethod = Literal["text", "table", "ocr", "fallback", "llm", "vision"]

BBox = tuple[float, float, float, float]  # (x0, y0, x1, y1) in PDF points


@dataclass(frozen=True)
class SourceLocation:
    """Where a fragment lives in the source document.

    ``bbox`` is the superset locator (Inv-Man-Intake). Pension-Data's string refs such as
    ``p.40#table`` are derivable from ``page`` + ``table_index`` via :class:`EvidenceRef`,
    so both consumers serialize losslessly.
    """

    source_doc_id: str
    source_page: int | None = None
    bbox: BBox | None = None
    table_index: int | None = None
    image_index: int | None = None


@dataclass(frozen=True)
class SnippetMetadata:
    """Replayable excerpt offsets for a field's supporting text (Inv-Man-Intake)."""

    kind: str
    char_start: int | None = None
    char_end: int | None = None


@dataclass(frozen=True)
class EvidenceRef:
    """Canonical, stable reference to supporting evidence (Pension-Data).

    ``ref_id`` is a content hash over the *locator only* — enrichment fields (``excerpt``,
    ``method``) are deliberately excluded so enriching a locator never changes its identity,
    exactly as Pension-Data's ``evidence_ref_id`` does.
    """

    source_doc_id: str
    page_number: int | None = None
    section_hint: str | None = None
    snippet_anchor: str | None = None
    method: ExtractionMethod | None = None
    excerpt: str | None = None

    @property
    def canonical(self) -> str:
        """Stable human-readable locator string.

        Mirrors Pension-Data's citation export forms: ``doc#page=n``, ``doc#anchor=…``,
        ``doc#section=…``, falling back to the bare doc id.
        """
        if self.snippet_anchor:
            return f"{self.source_doc_id}#anchor={self.snippet_anchor}"
        if self.page_number is not None:
            return f"{self.source_doc_id}#page={self.page_number}"
        if self.section_hint:
            return f"{self.source_doc_id}#section={self.section_hint}"
        return self.source_doc_id

    @property
    def ref_id(self) -> str:
        """Deterministic id over the locator (excludes enrichment fields)."""
        parts = (
            self.source_doc_id,
            "" if self.page_number is None else str(self.page_number),
            self.section_hint or "",
            self.snippet_anchor or "",
        )
        digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
        return f"evidence:{digest[:16]}"


# --- Raw modality output (Inv-Man-Intake): what a layout extractor emits ---------------


@dataclass(frozen=True)
class ExtractedTextBlock:
    text: str
    location: SourceLocation


@dataclass(frozen=True)
class ExtractedTableCell:
    row_index: int
    column_index: int
    value: str
    confidence: float | None = None


@dataclass(frozen=True)
class ExtractedTable:
    cells: tuple[ExtractedTableCell, ...]
    location: SourceLocation | None = None
    table_id: str | None = None


@dataclass(frozen=True)
class ExtractedImage:
    location: SourceLocation
    image_id: str | None = None
    mime_type: str | None = None
    ocr_text: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class ProviderExtractionOutput:
    """Raw multimodal extraction output, grouped by modality (Inv-Man-Intake)."""

    source_doc_id: str
    provider_name: str
    text_blocks: tuple[ExtractedTextBlock, ...] = ()
    tables: tuple[ExtractedTable, ...] = ()
    images: tuple[ExtractedImage, ...] = ()


# --- Field-level result (Inv-Man-Intake fields + Pension-Data outcome metadata) --------


@dataclass(frozen=True)
class ExtractedField:
    """One extracted field with evidence metadata."""

    key: str
    value: str
    confidence: float
    source_doc_id: str
    source_page: int
    method: str
    location: SourceLocation | None = None
    snippet: str | None = None
    snippet_metadata: SnippetMetadata | None = None
    evidence: EvidenceRef | None = None


@dataclass(frozen=True)
class ParserAttempt:
    """Structured record of one orchestration stage attempt (Pension-Data)."""

    stage_name: str
    parser_name: str
    succeeded: bool
    failure_reason: str | None = None


@dataclass(frozen=True)
class EscalationEvent:
    """Emitted when every fallback stage fails (Pension-Data)."""

    domain: str
    reason: str
    exhausted_stage_count: int
    attempts: tuple[ParserAttempt, ...]


@dataclass(frozen=True)
class ExtractedDocumentResult:
    """Canonical extraction result.

    Inv-Man-Intake's field-level result fused with Pension-Data's ``PDFParserResult``
    outcome metadata (stage / attempts / escalation / flags / provenance), so both
    consumers adopt one result type.
    """

    source_doc_id: str
    provider_name: str
    fields: tuple[ExtractedField, ...] = ()
    stage_name: str | None = None
    stage_confidence: float = 0.0
    attempts: tuple[ParserAttempt, ...] = ()
    escalation: EscalationEvent | None = None
    escalation_required: bool = False
    flags: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()


# --- Validators (Inv-Man-Intake, extended with Pension-Data strict-mode rule) ----------

# High-impact field families must carry an evidence ref in strict mode (Pension-Data).
HIGH_IMPACT_PREFIXES: tuple[str, ...] = ("funded", "actuarial", "allocation", "holding", "fee")


def _validate_source_location(
    location: SourceLocation, *, expected_source_doc_id: str, context: str
) -> None:
    if not location.source_doc_id:
        raise ValueError(f"SourceLocation.source_doc_id must be non-empty for {context}")
    if location.source_doc_id != expected_source_doc_id:
        raise ValueError(f"SourceLocation.source_doc_id must match output for {context}")
    if location.source_page is not None and location.source_page < 0:
        raise ValueError("SourceLocation.source_page must be >= 0 when provided")


def _validate_snippet_metadata(metadata: SnippetMetadata) -> None:
    if not metadata.kind.strip():
        raise ValueError("SnippetMetadata.kind must be non-empty")
    for name, value in (("char_start", metadata.char_start), ("char_end", metadata.char_end)):
        if value is not None and value < 0:
            raise ValueError(f"SnippetMetadata.{name} must be >= 0 when provided")
    if (
        metadata.char_start is not None
        and metadata.char_end is not None
        and metadata.char_end < metadata.char_start
    ):
        raise ValueError("SnippetMetadata.char_end must be >= char_start when provided")


def _validate_evidence_ref(
    evidence: EvidenceRef, *, expected_source_doc_id: str, context: str
) -> None:
    if not evidence.source_doc_id:
        raise ValueError(f"EvidenceRef.source_doc_id must be non-empty for {context}")
    if evidence.source_doc_id != expected_source_doc_id:
        raise ValueError(f"EvidenceRef.source_doc_id must match result for {context}")
    if evidence.page_number is not None and evidence.page_number <= 0:
        raise ValueError("EvidenceRef.page_number must be >= 1 when provided")


def validate_provider_output(output: ProviderExtractionOutput) -> None:
    """Validate raw multimodal output emitted by an extraction provider."""
    if not output.source_doc_id:
        raise ValueError("ProviderExtractionOutput.source_doc_id must be non-empty")
    if not output.provider_name:
        raise ValueError("ProviderExtractionOutput.provider_name must be non-empty")
    for block in output.text_blocks:
        _validate_source_location(
            block.location, expected_source_doc_id=output.source_doc_id, context="text_blocks"
        )
    for table in output.tables:
        if table.location is not None:
            _validate_source_location(
                table.location, expected_source_doc_id=output.source_doc_id, context="tables"
            )
        for cell in table.cells:
            if cell.confidence is not None and not 0.0 <= cell.confidence <= 1.0:
                raise ValueError("ExtractedTableCell.confidence must be within [0.0, 1.0]")
    for image in output.images:
        _validate_source_location(
            image.location, expected_source_doc_id=output.source_doc_id, context="images"
        )


def validate_extracted_document_result(
    result: ExtractedDocumentResult, *, strict_evidence: bool = False
) -> None:
    """Validate the canonical result.

    With ``strict_evidence=True``, high-impact fields (see :data:`HIGH_IMPACT_PREFIXES`)
    must carry an :class:`EvidenceRef` — Pension-Data's strict-mode provenance rule.
    """
    if not result.source_doc_id:
        raise ValueError("ExtractedDocumentResult.source_doc_id must be non-empty")
    if not result.provider_name:
        raise ValueError("ExtractedDocumentResult.provider_name must be non-empty")
    for f in result.fields:
        if not f.key:
            raise ValueError("ExtractedField.key must be non-empty")
        if not f.value:
            raise ValueError("ExtractedField.value must be non-empty")
        if not 0.0 <= f.confidence <= 1.0:
            raise ValueError("ExtractedField.confidence must be within [0.0, 1.0]")
        if f.source_doc_id != result.source_doc_id:
            raise ValueError("ExtractedField.source_doc_id must match the result")
        if f.source_page < 0:
            raise ValueError("ExtractedField.source_page must be >= 0")
        if not f.method.strip():
            raise ValueError("ExtractedField.method must be non-empty")
        if f.location is not None:
            _validate_source_location(
                f.location, expected_source_doc_id=result.source_doc_id, context=f"field:{f.key}"
            )
        if f.snippet_metadata is not None:
            _validate_snippet_metadata(f.snippet_metadata)
        if f.evidence is not None:
            _validate_evidence_ref(
                f.evidence, expected_source_doc_id=result.source_doc_id, context=f"field:{f.key}"
            )
        if strict_evidence and f.evidence is None:
            family = f.key.split(".", 1)[0].split("_", 1)[0].lower()
            if family in HIGH_IMPACT_PREFIXES:
                raise ValueError(
                    f"ExtractedField {f.key!r} is high-impact and requires an EvidenceRef "
                    "under strict_evidence"
                )


@runtime_checkable
class _HasName(Protocol):  # pragma: no cover - structural helper only
    @property
    def name(self) -> str: ...


__all__ = [
    "BBox",
    "ExtractionMethod",
    "SourceLocation",
    "SnippetMetadata",
    "EvidenceRef",
    "ExtractedTextBlock",
    "ExtractedTableCell",
    "ExtractedTable",
    "ExtractedImage",
    "ProviderExtractionOutput",
    "ExtractedField",
    "ParserAttempt",
    "EscalationEvent",
    "ExtractedDocumentResult",
    "HIGH_IMPACT_PREFIXES",
    "validate_provider_output",
    "validate_extracted_document_result",
]
