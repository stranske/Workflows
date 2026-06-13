"""Validate workflow filenames referenced by docs/ci/WORKFLOWS.md exist."""

from __future__ import annotations

import re
from pathlib import Path

WORKFLOWS_DOC = Path("docs/ci/WORKFLOWS.md")
# A referenced workflow is valid if it ships in the Workflows repo root or in the
# consumer-repo template. The consumer-default event hub pair
# (agents-80-pr-event-hub.yml, agents-81-gate-followups.yml) lives only in the
# template, so checking the root directory alone reports spurious dangling links.
WORKFLOW_DIRS = (
    Path(".github/workflows"),
    Path("templates/consumer-repo/.github/workflows"),
)
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
    dangling = [
        name
        for name in references
        if not any((directory / name).is_file() for directory in WORKFLOW_DIRS)
    ]

    print(f"workflow references checked: {len(references)}")
    print(f"dangling workflow references: {dangling}")

    assert references, "docs/ci/WORKFLOWS.md should reference at least one workflow file"
    assert not dangling, f"Dangling workflow reference(s): {dangling}"
