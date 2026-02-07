"""Validate verification concern documentation structure and evidence links."""

from __future__ import annotations

import re
from pathlib import Path

DOC_PATH = Path("docs/verification-concerns-1307.md")

REQUIRED_SUBSECTIONS = (
    "#### Resolution summary",
    "#### Resolution link",
    "#### DECISIONS.md reference",
    "#### Evidence",
)

LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _concern_sections(text: str) -> list[str]:
    lines = text.splitlines()
    indices = [i for i, line in enumerate(lines) if line.startswith("### ")]
    sections: list[str] = []
    for idx, start in enumerate(indices):
        end = indices[idx + 1] if idx + 1 < len(indices) else len(lines)
        sections.append("\n".join(lines[start:end]))
    return sections


def _resolve_evidence_path(link: str) -> Path | None:
    if not ("reverification/" in link):
        return None

    if link.startswith("docs/reverification/"):
        return Path(link)
    if link.startswith("reverification/"):
        return Path("docs") / link
    if link.startswith("../docs/reverification/"):
        return Path(link.lstrip("../"))
    if link.startswith("./reverification/"):
        return Path("docs") / link.removeprefix("./")
    return Path(link)


def test_verification_concerns_have_required_subsections_and_evidence_links() -> None:
    text = DOC_PATH.read_text(encoding="utf-8")
    sections = _concern_sections(text)

    assert sections, "Expected at least one verification concern section"

    for section in sections:
        for subsection in REQUIRED_SUBSECTIONS:
            assert subsection in section, f"Missing subsection {subsection}"

        links = LINK_RE.findall(section)
        evidence_paths = [
            path for link in links if (path := _resolve_evidence_path(link)) is not None
        ]

        assert evidence_paths, "Expected evidence link under docs/reverification/"

        for path in evidence_paths:
            assert path.exists(), f"Evidence path missing: {path}"


def test_verification_concerns_reference_decisions_entry() -> None:
    text = DOC_PATH.read_text(encoding="utf-8")
    sections = _concern_sections(text)

    for section in sections:
        assert "DECISIONS.md" in section
        assert "DECISIONS.md#" in section
