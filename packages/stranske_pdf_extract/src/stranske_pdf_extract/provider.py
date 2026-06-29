"""Extraction provider Protocols, the OCR injection seam, and a name registry.

The two ``@runtime_checkable`` Protocols are lifted from Inv-Man-Intake — they are
already the right seam. Docling, the pure-python baseline, OCR, and managed APIs
(Textract/Azure) are all just providers behind these Protocols, resolved by name.

The OCR seam is Pension-Data's idea promoted to a named type: a repo can **bundle**
Tesseract (Counter_Risk) or **inject** its own callable (Pension-Data). The library
never hard-codes an OCR engine.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol, runtime_checkable

from .contract import ExtractedDocumentResult, ProviderExtractionOutput

# Injectable OCR: bytes -> per-page text. None means "OCR not configured" (graceful skip).
OcrExtract = Callable[[bytes], Sequence[str]]


@runtime_checkable
class ExtractionProvider(Protocol):
    """Field-level provider: raw bytes -> canonical document result."""

    @property
    def name(self) -> str:
        """Stable provider name used in orchestration logs and the registry."""
        ...

    def extract(self, source_doc_id: str, content: bytes) -> ExtractedDocumentResult:
        """Extract canonical fields from raw document bytes."""
        ...


@runtime_checkable
class MultiModalExtractionProvider(Protocol):
    """Raw-modality provider: bytes -> text/table/image output (e.g. Docling)."""

    @property
    def name(self) -> str:
        """Stable provider name used in orchestration logs and the registry."""
        ...

    def extract_modalities(self, source_doc_id: str, content: bytes) -> ProviderExtractionOutput:
        """Extract text, table, and image outputs from raw document bytes."""
        ...


# --- Minimal name registry -------------------------------------------------------------

_PROVIDERS: dict[str, Callable[..., object]] = {}


def register_provider(name: str, factory: Callable[..., object]) -> None:
    """Register a provider factory under a stable name.

    ``factory`` is called lazily (so optional heavy deps are imported only on use).
    Re-registering the same name overwrites — last registration wins.
    """
    if not name.strip():
        raise ValueError("provider name must be non-empty")
    _PROVIDERS[name] = factory


def build_provider(name: str, **kwargs: object) -> object:
    """Instantiate a registered provider by name."""
    try:
        factory = _PROVIDERS[name]
    except KeyError:
        raise KeyError(f"unknown provider {name!r}; registered: {sorted(_PROVIDERS)}") from None
    return factory(**kwargs)


def registered_providers() -> tuple[str, ...]:
    return tuple(sorted(_PROVIDERS))


__all__ = [
    "OcrExtract",
    "ExtractionProvider",
    "MultiModalExtractionProvider",
    "register_provider",
    "build_provider",
    "registered_providers",
]
