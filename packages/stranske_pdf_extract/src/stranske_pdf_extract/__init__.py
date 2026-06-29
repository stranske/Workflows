"""stranske-pdf-extract — single-source PDF extraction for the stranske/* fleet.

Public surface:

* :mod:`stranske_pdf_extract.contract` — the one result + page-level-provenance contract.
* :mod:`stranske_pdf_extract.provider` — provider Protocols, OCR seam, name registry.
* :mod:`stranske_pdf_extract.orchestration` — the fallback-ladder primitive.
* :mod:`stranske_pdf_extract.reliability` — arithmetic/business-rule checks, cross-check,
  calibration + confidence routing.

Providers live under :mod:`stranske_pdf_extract.providers`. Domain field-parsing stays in
each consumer — this package never learns a consumer's schema. See ``docs/DESIGN.md``.
"""

from __future__ import annotations

__version__ = "0.1.0"

from . import contract, orchestration, provider, reliability

__all__ = ["contract", "provider", "orchestration", "reliability", "__version__"]
