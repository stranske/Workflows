"""Docling-backed real extractor behind ``MultiModalExtractionProvider``.

Docling (IBM, **MIT**, local) is the primary real extractor for proprietary fleet docs:
layout model + TableFormer tables, no per-page fee, nothing leaves the building
(methodology doc §1, §7). It is a heavy native dep, so it is an **optional extra**
(``pip install stranske-pdf-extract[docling]``) and is never imported by browser
(stlite/Pyodide) paths.

This is the single REAL extractor required by the scaffold deliverable, and the shared
implementation that Inv-Man-Intake #713 should CONSUME instead of writing a 5th private
Docling provider. The class conforms to the Protocol whether or not Docling is installed;
calling :meth:`extract_modalities` without the dep raises a clear, actionable error.
"""

from __future__ import annotations

from ..contract import (
    ExtractedTable,
    ExtractedTableCell,
    ExtractedTextBlock,
    ProviderExtractionOutput,
    SourceLocation,
)
from ..provider import register_provider


class DoclingUnavailableError(RuntimeError):
    """Raised when the optional ``docling`` extra is not installed."""


def docling_available() -> bool:
    """True when the optional ``docling`` dependency can be imported."""
    try:
        import docling  # noqa: F401
    except Exception:  # noqa: BLE001 - any import failure means "unavailable"
        return False
    return True


class DoclingProvider:
    """Map a ``DoclingDocument`` onto the shared modality contract."""

    name = "docling"

    def __init__(self, *, do_ocr: bool = False) -> None:
        # Stored, not used until extract — construction must not require the heavy dep,
        # so the Protocol-conformance test can run with the extra absent.
        self._do_ocr = do_ocr

    def extract_modalities(self, source_doc_id: str, content: bytes) -> ProviderExtractionOutput:
        if not docling_available():
            raise DoclingUnavailableError(
                "the 'docling' extra is not installed; "
                "install with: pip install stranske-pdf-extract[docling]"
            )
        return self._extract_real(source_doc_id, content)

    def _extract_real(
        self, source_doc_id: str, content: bytes
    ) -> ProviderExtractionOutput:  # pragma: no cover - requires the optional heavy dep
        import io

        from docling.datamodel.base_models import (
            DocumentStream,  # type: ignore[import-not-found]
            InputFormat,  # type: ignore[import-not-found]
        )
        from docling.datamodel.pipeline_options import (  # type: ignore[import-not-found]
            PdfPipelineOptions,
        )
        from docling.document_converter import (
            DocumentConverter,  # type: ignore[import-not-found]
            PdfFormatOption,  # type: ignore[import-not-found]
        )

        source = DocumentStream(name=source_doc_id, stream=io.BytesIO(content))
        pipeline_options = PdfPipelineOptions(do_ocr=self._do_ocr)
        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
            }
        )
        document = converter.convert(source).document

        text_blocks: list[ExtractedTextBlock] = []
        tables: list[ExtractedTable] = []

        for item, _level in document.iterate_items():
            page_no = _page_of(item)
            bbox = _bbox_of(item)
            text = getattr(item, "text", None)
            if text:
                text_blocks.append(
                    ExtractedTextBlock(
                        text=text,
                        location=SourceLocation(
                            source_doc_id=source_doc_id, source_page=page_no, bbox=bbox
                        ),
                    )
                )

        for t_index, table in enumerate(getattr(document, "tables", []) or []):
            cells = tuple(
                ExtractedTableCell(
                    row_index=getattr(cell, "start_row_offset_idx", 0),
                    column_index=getattr(cell, "start_col_offset_idx", 0),
                    value=str(getattr(cell, "text", "")),
                )
                for cell in getattr(getattr(table, "data", None), "table_cells", []) or []
            )
            tables.append(
                ExtractedTable(
                    cells=cells,
                    location=SourceLocation(
                        source_doc_id=source_doc_id,
                        source_page=_page_of(table),
                        table_index=t_index,
                    ),
                    table_id=f"table-{t_index}",
                )
            )

        return ProviderExtractionOutput(
            source_doc_id=source_doc_id,
            provider_name=self.name,
            text_blocks=tuple(text_blocks),
            tables=tuple(tables),
        )


def _page_of(item: object) -> int | None:  # pragma: no cover - exercised with the dep
    prov = getattr(item, "prov", None) or []
    if prov:
        return getattr(prov[0], "page_no", None)
    return None


def _bbox_of(item: object):  # pragma: no cover - exercised with the dep
    prov = getattr(item, "prov", None) or []
    if not prov:
        return None
    bbox = getattr(prov[0], "bbox", None)
    if bbox is None:
        return None
    return (
        getattr(bbox, "l", 0.0),
        getattr(bbox, "t", 0.0),
        getattr(bbox, "r", 0.0),
        getattr(bbox, "b", 0.0),
    )


register_provider("docling", DoclingProvider)

__all__ = ["DoclingProvider", "DoclingUnavailableError", "docling_available"]
