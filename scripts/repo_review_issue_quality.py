"""Quality checks for weekly repo-review issue bodies."""

from __future__ import annotations

import re

ISSUE_BODY_REQUIRED_SECTIONS = (
    "## Why",
    "## Scope",
    "## Non-Goals",
    "## Tasks",
    "## Acceptance Criteria",
    "## Implementation Notes",
)

GENERIC_PHRASES = (
    "approved weekly-review candidate",
    "candidate source:",
    "weekly priority:",
    "implement the approved review gap",
    "add or update repo-local tests",
    "the reviewed design/readiness gap",
    "implemented in repo-local code, docs, tests, or workflows as appropriate",
    "no unrelated workflows/template-sync",
    "use the file paths named in the scope/tasks as the starting point",
    "ready to upload if approved",
)

FRAGMENT_TASKS = {
    "strip leading/trailing whitespace",
    "collapse repeated spaces",
    "normalize apostrophes/hyphens where appropriate",
}


def markdown_section(body: str, heading: str) -> str:
    match = re.search(rf"(?ms)^{re.escape(heading)}\s*\n(.*?)(?=^## |\Z)", body)
    return match.group(1).strip() if match else ""


def checklist_items(section_text: str) -> list[str]:
    return [
        match.group(1).strip()
        for match in re.finditer(r"(?m)^- \[[ xX]\]\s+(.+)$", section_text)
    ]


def issue_body_quality_errors(body: str) -> list[str]:
    errors: list[str] = []
    normalized = body.lower()

    for section in ISSUE_BODY_REQUIRED_SECTIONS:
        if not re.search(rf"(?m)^{re.escape(section)}\s*$", body):
            errors.append(f"missing required section {section}")

    for phrase in GENERIC_PHRASES:
        if phrase in normalized:
            errors.append(f"generic placeholder phrase: {phrase}")

    tasks = checklist_items(markdown_section(body, "## Tasks"))
    acceptance = checklist_items(markdown_section(body, "## Acceptance Criteria"))
    if len(tasks) < 4:
        errors.append("fewer than 4 task checkboxes")
    if len(acceptance) < 3:
        errors.append("fewer than 3 acceptance-criteria checkboxes")

    for item in tasks:
        lowered = item.lower().strip()
        if item.endswith(":"):
            errors.append(f"task checkbox is a fragment ending with colon: {item}")
        if lowered in FRAGMENT_TASKS:
            errors.append(f"task checkbox is a fragment: {item}")
        if len(item.split()) < 4:
            errors.append(f"task checkbox is too terse: {item}")

    for item in acceptance:
        if item.endswith(":"):
            errors.append(f"acceptance checkbox is a fragment ending with colon: {item}")
        if len(item.split()) < 6:
            errors.append(f"acceptance checkbox is too terse: {item}")

    implementation_notes = markdown_section(body, "## Implementation Notes")
    if implementation_notes:
        if "relevant areas:" in implementation_notes.lower():
            errors.append("implementation notes use broad 'Relevant areas' wording")
        if not re.search(r"`[^`]+`", implementation_notes):
            errors.append("implementation notes do not include concrete path/code references")

    return errors


def issue_body_is_agent_ready(body: str) -> bool:
    return not issue_body_quality_errors(body)
