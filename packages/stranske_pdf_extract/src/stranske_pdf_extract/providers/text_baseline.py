"""Pure-python baseline extractor: pdfplumber -> pypdf -> injected OCR -> raw decode.

This is Counter_Risk's graceful-degradation ladder, generalized to emit the shared
``ProviderExtractionOutput``. Every stage is import-guarded so the provider runs (and
the test suite passes) with **no** native deps installed: it degrades to a latin-1
decode of native-text bytes, exactly like Pension-Data's fallback. Real consumers add
``[baseline]`` (pdfplumber/pypdf) and/or an injected ``OcrExtract`` callable.
"""

from __future__ import annotations

import logging

from ..contract import (
    ExtractedTextBlock,
    ProviderExtractionOutput,
    SourceLocation,
)
from ..provider import MultiModalExtractionProvider, OcrExtract, register_provider

_log = logging.getLogger(__name__)


class TextBaselineProvider:
    """Native-text ladder emitting one text block per page."""

    name = "text_baseline"

    def __init__(self, *, ocr_extract: OcrExtract | None = None) -> None:
        self._ocr_extract = ocr_extract

    def extract_modalities(self, source_doc_id: str, content: bytes) -> ProviderExtractionOutput:
        pages = (
            self._usable_pages(self._with_pdfplumber(content))
            or self._usable_pages(self._with_pypdf(content))
            or self._usable_pages(self._with_ocr(content))
            or self._usable_pages(self._raw_decode(content))
            or []
        )
        blocks = tuple(
            ExtractedTextBlock(
                text=text,
                location=SourceLocation(source_doc_id=source_doc_id, source_page=i),
            )
            for i, text in enumerate(pages, start=1)
            if text.strip()
        )
        return ProviderExtractionOutput(
            source_doc_id=source_doc_id, provider_name=self.name, text_blocks=blocks
        )

    def _with_pdfplumber(self, content: bytes) -> list[str]:
        try:
            import io

            import pdfplumber
        except ImportError:
            return []
        try:
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                return [page.extract_text() or "" for page in pdf.pages]
        except Exception:  # noqa: BLE001 - fall through to next ladder stage
            _log.warning("pdfplumber failed for %s", source_doc_id_safe(content), exc_info=True)
            return []

    def _with_pypdf(self, content: bytes) -> list[str]:
        try:
            import io

            from pypdf import PdfReader
        except ImportError:
            return []
        try:
            reader = PdfReader(io.BytesIO(content), strict=False)
            return [page.extract_text() or "" for page in reader.pages]
        except Exception:  # noqa: BLE001
            return []

    def _with_ocr(self, content: bytes) -> list[str]:
        if self._ocr_extract is None:
            return []
        try:
            return [t for t in self._ocr_extract(content) if isinstance(t, str)]
        except Exception:  # noqa: BLE001
            _log.warning("injected OCR failed", exc_info=True)
            return []

    @staticmethod
    def _usable_pages(pages: list[str]) -> list[str]:
        return pages if any(page.strip() for page in pages) else []

    @staticmethod
    def _raw_decode(content: bytes) -> list[str]:
        # Last resort: native-text bytes / sanitized .pdf test fixtures.
        decoded = content.decode("latin-1", errors="ignore")
        normalized = decoded.replace("\r\n", "\n").replace("\r", "\n")
        if "\f" in normalized:
            return normalized.split("\f")
        return [normalized]


def source_doc_id_safe(content: bytes) -> str:  # pragma: no cover - log helper
    return f"<{len(content)} bytes>"


# Confirm the class satisfies the Protocol at import time (cheap structural check).
assert isinstance(TextBaselineProvider(), MultiModalExtractionProvider)

register_provider("text_baseline", TextBaselineProvider)

__all__ = ["TextBaselineProvider"]
