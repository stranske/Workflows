"""Provider conformance.

``test_docling_provider_conforms_to_protocol`` is the named acceptance gate for the
build issue: the real Docling provider must satisfy the runtime-checkable Protocol
WHETHER OR NOT the heavy optional dep is installed (construction must not require it).
This mirrors Inv-Man-Intake #713's conformance test, which should point at this shared
provider rather than a private re-implementation.
"""

from __future__ import annotations

from stranske_pdf_extract.provider import (
    MultiModalExtractionProvider,
    build_provider,
    registered_providers,
)
from stranske_pdf_extract.providers import (
    DoclingProvider,
    DoclingUnavailableError,
    TextBaselineProvider,
    docling_available,
)


def test_docling_provider_conforms_to_protocol():
    # Construction never requires the optional dep; conformance holds regardless.
    provider = DoclingProvider()
    assert isinstance(provider, MultiModalExtractionProvider)
    assert provider.name == "docling"


def test_docling_extract_raises_clearly_without_dep():
    if docling_available():
        import pytest

        pytest.skip("docling installed; the no-dep error path is not exercised")
    provider = DoclingProvider()
    try:
        provider.extract_modalities("doc1", b"%PDF-1.4 ...")
    except DoclingUnavailableError as exc:
        assert "pip install" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected DoclingUnavailableError without the docling extra")


def test_baseline_provider_conforms_and_extracts_text():
    provider = TextBaselineProvider()
    assert isinstance(provider, MultiModalExtractionProvider)
    # Pure-python ladder degrades to a raw decode on native-text bytes (no deps needed).
    out = provider.extract_modalities("doc1", b"Funded ratio 84%\fPage two text")
    assert out.provider_name == "text_baseline"
    assert len(out.text_blocks) == 2
    assert out.text_blocks[0].location.source_page == 1
    assert "Funded ratio" in out.text_blocks[0].text


def test_registry_resolves_providers_by_name():
    assert {"docling", "text_baseline"} <= set(registered_providers())
    assert isinstance(build_provider("text_baseline"), TextBaselineProvider)
    assert isinstance(build_provider("docling"), DoclingProvider)
