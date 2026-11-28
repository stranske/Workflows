"""Validate verification concern documentation structure and evidence links."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

DOC_PATH = Path("docs/reverification/verification-concerns-1307.md").resolve()
EVIDENCE_DIR = DOC_PATH.parent
DECISIONS_PATH = EVIDENCE_DIR / "DECISIONS.md"
INDEX_PATH = EVIDENCE_DIR / "README.md"
MISSING_ARTIFACTS_CONCERN = "### Missing verification concerns/artifacts (Severity: High)"
MISSING_ARTIFACTS_DECISION = "2026-02-07---pr-1307-missing-verification-artifacts"

REQUIRED_SUBSECTIONS = (
    "#### Resolution summary",
    "#### Resolution link",
    "#### DECISIONS.md reference",
    "#### Evidence",
)

LINK_RE = re.compile(r"(?<![\\!])\[[^\]]+\]\(([^\s)]+)\)")
NON_RENDERED_RE = re.compile(
    r"<!--.*?(?:-->|\Z)"
    r"|^ {0,3}(?P<fence>`{3,}|~{3,})[^\n]*\n.*?(?:^ {0,3}(?P=fence)[ \t]*$|\Z)"
    r"|(?<!`)(?P<ticks>`+)(?!`).*?(?<!`)(?P=ticks)(?!`)",
    re.M | re.S,
)


def _visible_markdown(path: Path) -> str:
    """Mask Markdown comments and code before checking links and anchors."""
    return NON_RENDERED_RE.sub(
        lambda match: re.sub(r"[^\n]", " ", match[0]), path.read_text(encoding="utf-8")
    )


def _sections(text: str, heading_prefix: str) -> list[str]:
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith(heading_prefix)]
    ends = [*starts[1:], len(lines)]
    return ["\n".join(lines[start:end]) for start, end in zip(starts, ends, strict=False)]


def _subsection_links(section: str, heading: str) -> list[str]:
    match = re.search(rf"^{re.escape(heading)}\n(.*?)(?=^#{{1,4}} |\Z)", section, re.M | re.S)
    assert match is not None, f"Missing subsection {heading}"
    return LINK_RE.findall(match[1])


def _local_path(source: Path, link: str) -> Path | None:
    url = urlsplit(link)
    if url.scheme or url.netloc or not url.path:
        return None
    return (source.parent / unquote(url.path)).resolve()


def _evidence_paths(source: Path, links: list[str]) -> set[Path]:
    evidence = {
        path
        for link in links
        if (path := _local_path(source, link)) is not None
        and path.is_relative_to(EVIDENCE_DIR)
        and path not in {DECISIONS_PATH, INDEX_PATH}
    }
    assert evidence, "Expected evidence link under docs/reverification/"
    for path in evidence:
        assert path.is_file(), f"Evidence path missing: {path}"
    return evidence


def test_verification_concerns_have_required_subsections_and_evidence_links() -> None:
    sections = _sections(_visible_markdown(DOC_PATH), "### ")
    assert sections, "Expected at least one verification concern section"

    for section in sections:
        for subsection in REQUIRED_SUBSECTIONS:
            assert subsection in section.splitlines(), f"Missing subsection {subsection}"
        _evidence_paths(DOC_PATH, LINK_RE.findall(section))
        _evidence_paths(DOC_PATH, _subsection_links(section, "#### Evidence"))


def test_verification_concerns_reference_decisions_entry() -> None:
    sections = _sections(_visible_markdown(DOC_PATH), "### ")
    assert sections, "Expected at least one verification concern section"
    decision_entries = {
        re.sub(r"[^\w -]", "", entry.splitlines()[0].removeprefix("## ").lower()).replace(
            " ", "-"
        ): entry
        for entry in _sections(_visible_markdown(DECISIONS_PATH), "## ")
    }

    assert any(section.splitlines()[0] == MISSING_ARTIFACTS_CONCERN for section in sections)
    for section in sections:
        links = _subsection_links(section, "#### DECISIONS.md reference")
        assert links, "Expected a decision link"
        for link in links:
            assert _local_path(DOC_PATH, link) == DECISIONS_PATH, f"Wrong decision path: {link}"
            anchor = unquote(urlsplit(link).fragment)
            assert anchor in decision_entries, f"Decision anchor missing: {link}"
            if section.splitlines()[0] == MISSING_ARTIFACTS_CONCERN:
                assert anchor == MISSING_ARTIFACTS_DECISION, f"Wrong decision anchor: {link}"
                decision_evidence = _evidence_paths(
                    DECISIONS_PATH, LINK_RE.findall(decision_entries[anchor])
                )
                concern_evidence = _evidence_paths(
                    DOC_PATH, _subsection_links(section, "#### Evidence")
                )
                assert decision_evidence & concern_evidence, "Decision and concern evidence differ"


def test_reverification_index_links_to_decisions_and_preserves_auth_anchor() -> None:
    links = LINK_RE.findall(_visible_markdown(INDEX_PATH))
    assert any(_local_path(INDEX_PATH, link) == DECISIONS_PATH for link in links)
    assert '<a id="auth-coverage-artifact-2026-02-08"></a>' in _visible_markdown(DECISIONS_PATH)
