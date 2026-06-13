"""Validate workflow filenames referenced by docs/ci/WORKFLOWS.md exist."""

from __future__ import annotations

import re
from pathlib import Path


WORKFLOWS_DOC = Path("docs/ci/WORKFLOWS.md")
WORKFLOW_DIR = Path(".github/workflows")
WORKFLOW_LINK_RE = re.compile(r"\]\(\.\./\.\./\.github/workflows/([^)#]+\.yml)(?:#[^)]+)?\)")
BACKTICK_WORKFLOW_RE = re.compile(r"`\.?([A-Za-z0-9][A-Za-z0-9_.-]+\.yml)`")


def _workflow_references() -> list[str]:
    contents = WORKFLOWS_DOC.read_text(encoding="utf-8")
    references = set(WORKFLOW_LINK_RE.findall(contents))

    for candidate in BACKTICK_WORKFLOW_RE.findall(contents):
        if "*" not in candidate and "/" not in candidate:
            references.add(candidate)

    return sorted(references)


def test_workflows_doc_references_existing_workflow_files() -> None:
    references = _workflow_references()
    dangling = [name for name in references if not (WORKFLOW_DIR / name).is_file()]

    print(f"workflow references checked: {len(references)}")
    print(f"dangling workflow references: {dangling}")

    assert references, "docs/ci/WORKFLOWS.md should reference at least one workflow file"
    assert not dangling, f"Dangling workflow reference(s): {dangling}"
