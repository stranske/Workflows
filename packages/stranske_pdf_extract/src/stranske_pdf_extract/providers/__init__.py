"""Extraction providers behind the shared Protocols.

Importing this package registers the always-available pure-python baseline and the
(optional-dep) Docling provider factory by name. Importing ``DoclingProvider`` does not
require the ``docling`` extra; only calling ``extract_modalities`` does.
"""

from __future__ import annotations

from .docling_provider import DoclingProvider, DoclingUnavailableError, docling_available
from .text_baseline import TextBaselineProvider

__all__ = [
    "TextBaselineProvider",
    "DoclingProvider",
    "DoclingUnavailableError",
    "docling_available",
]
