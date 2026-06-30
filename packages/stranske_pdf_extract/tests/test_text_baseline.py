"""Pure-python text baseline fallback behavior."""

from __future__ import annotations

from stranske_pdf_extract.providers.text_baseline import TextBaselineProvider


def test_blank_native_pages_fall_through_to_ocr(monkeypatch):
    provider = TextBaselineProvider(ocr_extract=lambda _content: ["ocr page"])
    monkeypatch.setattr(provider, "_with_pdfplumber", lambda _content: ["   "])
    monkeypatch.setattr(provider, "_with_pypdf", lambda _content: ["\n"])

    output = provider.extract_modalities("doc1", b"%PDF")

    assert [block.text for block in output.text_blocks] == ["ocr page"]
